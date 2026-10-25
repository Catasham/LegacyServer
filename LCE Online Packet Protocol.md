# LCE Online Packet Protocol

Oct 24, 2026 · @Tate

## Overview

The Windows64 build speaks a Java Edition 1.6-era packet protocol (one-byte packet IDs, big-endian fields) wrapped in 4-byte length-prefixed TCP frames. 4J added about 30 console-only packets on top of it. No public documentation of this protocol exists, so everything here is read from the MinecraftConsoles source (`minecraft-console`, commit `09df8928`, May 2026).

- **Scope:** the Windows64 TCP transport (`WinsockNetLayer`) used by the PC client and `Minecraft.Server`. Console platforms (Xbox Live, PSN) wrap the same packets in their own transports, which are not covered.
- **360 Revived:** its source is not public. It is a fork of this codebase from late June 2026, so the packet set should match closely, but it has not been verified against a 360 Revived client.
- **Closest existing material:** the [Minecraft Community Edition packets page](https://mintlify.wiki/Minecraft-Community-Edition/client/api/packets) names about 27 packet classes with C++ member lists, but gives no byte-level layouts. The old Java protocol (wiki.vg, protocol 78) is a useful cross-reference, but many LCE packets differ from it.

## Transport and framing

Game traffic runs over one TCP connection per player on port 25565, and every TCP message is a 4-byte big-endian length followed by that many bytes of packet stream. LAN games are announced separately over UDP broadcast on port 25566.

### TCP connection

1. The client connects to the server's TCP port (default 25565; `server-port` in `server.properties`). `TCP_NODELAY` is set on both ends.
2. **Before any framing**, the server sends one raw byte: the client's **smallId** (0–254), a slot number used to address that player.
3. If the server refuses the connection, it sends 6 raw bytes instead and then closes the socket: `0xFF`, `0xFF` (the Disconnect packet ID), then a big-endian int32 disconnect reason (for example `ServerFull`). If the server is not yet in play state, it closes the socket without sending anything.
4. Everything after that byte is framed in both directions.

### Frames

| Field | Type | Notes |
| --- | --- | --- |
| length | uint32, big-endian | 1 to 4,194,304 (4 MiB); anything else drops the connection |
| payload | `length` bytes | a chunk of the packet stream |

Frame boundaries do **not** line up with packets. The sender writes packets into a 5 KiB buffered stream and flushes it as frames, so one frame can hold several packets, and a packet can be split across frames. A receiver must append every payload to one byte buffer per connection and parse packets from that buffer.

### Packets inside the stream

Each packet is one unsigned byte of packet ID followed by its fields, with **no length field**. The only way to find where a packet ends is to decode its fields, so an unknown or mis-parsed packet desynchronises the whole connection. A receiver silently drops any packet ID that is not registered for its direction (see the ID table).

### Primitive types

All multi-byte values are big-endian, as in Java's `DataOutputStream`.

| Name            | Encoding                                                                                                                                                         |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| byte / ubyte    | 1 byte                                                                                                                                                           |
| bool            | 1 byte, 0 or 1                                                                                                                                                   |
| short           | int16                                                                                                                                                            |
| int             | int32                                                                                                                                                            |
| long            | int64                                                                                                                                                            |
| float / double  | IEEE 754, 4 / 8 bytes                                                                                                                                            |
| string          | int16 length in UTF-16 code units, then that many UTF-16BE code units (not UTF-8). A length of 0 or less, or above the reader's limit, reads as an empty string. |
| PlayerUID       | int64 on Windows64 (an XUID-style player ID)                                                                                                                     |
| item            | int16 item ID; `-1` = empty slot and nothing follows. Otherwise: byte count, int16 damage/aux value, then an NBT blob                                            |
| NBT blob        | int16 length; `-1` (or 0) = no tag. Otherwise `length` bytes of **uncompressed** NBT (Java gzips this; 4J removed the gzip)                                      |
| entity metadata | repeated entries of 1 header byte (`type << 5` OR `id`, id 0–31) + value; ends with the byte `0x7F`. Types: 0 byte, 1 short, 2 int, 3 float, 4 string, 5 item    |

### LAN discovery (UDP)

A host advertising a LAN game broadcasts an 84-byte datagram to `255.255.255.255:25566` once per second. Unlike game traffic, it is a packed C struct in **little-endian** byte order.

| Offset | Field | Type |
| --- | --- | --- |
| 0 | magic | uint32 `0x4D434C4E` |
| 4 | netVersion | uint16 (560 in this build) |
| 6 | gamePort | uint16 (the TCP port) |
| 8 | hostName | 32 × UTF-16LE, null-padded |
| 72 | playerCount | uint8 |
| 73 | maxPlayers | uint8 |
| 74 | gameHostSettings | uint32 bit flags |
| 78 | texturePackParentId | uint32 |
| 82 | subTexturePackId | uint8 |
| 83 | isJoinable | uint8 |

Listeners ignore datagrams shorter than 84 bytes or with the wrong magic. Byte 72 follows the 64-byte host name.

## Connection flow

A client joins with two round trips, PreLogin (2) then Login (1), and must finish them within 30 seconds (600 ticks). It is then kept alive by KeepAlive (0) packets that each side sends every 20 ticks. The server is `PendingConnection` until login succeeds and `PlayerConnection` after.

### Join sequence

&#91;embedded content: join handshake · client and server, 9 steps\]

The numbers match the steps below. Only steps 2 and 4 can end in a rejection, and the server's Login (6) is the first packet it sends after accepting the player.

1. **TCP accept.** The server sends the raw smallId byte (see Transport).
2. **C→S PreLogin (2)** carrying the player name and `netcodeVersion` = 560. A mismatch is answered with Disconnect `OutdatedServer` (13) if the client is newer, or `OutdatedClient` (14) if it is older.
3. **S→C PreLogin (2)**: name `"-"`, the online XUIDs of players already in the game, the world's unique save name, the host option bit field, and the texture pack ID.
4. **C→S Login (1)** carrying the name, `clientVersion` = 78, offline and online XUIDs, privileges, and skin and cape IDs. A version mismatch is rejected the same way as in step 2. The server then rejects banned, non-whitelisted, duplicate-XUID or (optionally) duplicate-name players with Disconnect `Banned` (25).
5. **Skin requests (optional).** If the player's skin or cape is custom and not cached, the server sends TextureAndGeometry (160) or Texture (154) asking for the data.
6. **S→C Login (1)**: the player's entity ID, level type, seed, game mode, dimension, max build height, max players, difficulty, the player's index, privileges, world XZ size and Nether scale.
7. **S→C world setup**, in this order: SetSpawnPosition (6), PlayerAbilities (202), SetCarriedItem (16), scoreboard packets (206–209), SetTime (4), GameEvent (70) for rain, XZ (166) for the stronghold, then a Chat (3) "joined the game" broadcast to everyone.
8. **S→C chunks and position.** The server ticks the player once to send the nearest chunks (ChunkVisibility 50, BlockRegionUpdate 51), then teleports it with MovePlayer.PosRot (13). This is followed by SetTime (4), one UpdateMobEffect (41) per active effect, and the inventory (ContainerSetContent 104, then ContainerSetSlot 103 with window −1 and slot −1 for the item on the cursor).
9. **Play.** The client answers the teleport with its own MovePlayer packets. From here on, either side may send any packet registered for its direction.

### Staying connected

- Each side sends KeepAlive (0, an int32 ID) every 20 ticks (about 1 second).
- A connection with no incoming packets for 1,200 ticks (60 s) is closed with `TimeOut` (9), but only in builds with `CONNECTION_ENABLE_TIMEOUT_DISCONNECT` set.
- A side that leaves sends Disconnect (255) with a reason and closes the socket. Unexpected packets during login are answered with `UnexpectedPacket` (15).

### Disconnect reasons (int32, Windows64 numbering)

| Value | Reason | Value | Reason |
| --- | --- | --- | --- |
| 0 | None | 14 | OutdatedClient |
| 1 | Quitting | 15 | UnexpectedPacket |
| 2 | Closed | 16 | ConnectionCreationFailed |
| 3 | LoginTooLong | 17 | NoMultiplayerPrivilegesHost |
| 4 | IllegalStance | 18 | NoMultiplayerPrivilegesJoin |
| 5 | IllegalPosition | 19 | NoUGC\_AllLocal |
| 6 | MovedTooQuickly | 20 | NoUGC\_Single\_Local |
| 7 | NoFlying | 21 | ContentRestricted\_AllLocal |
| 8 | Kicked | 22 | ContentRestricted\_Single\_Local |
| 9 | TimeOut | 23 | NoUGC\_Remote |
| 10 | Overflow | 24 | NoFriendsInGame |
| 11 | EndOfStream | 25 | Banned |
| 12 | ServerFull | 26 | NotFriendsWithHost |
| 13 | OutdatedServer | 27 | NATMismatch |

The numbering is platform-dependent: PS3 builds lack `NoUGC_Remote`, which shifts every later value down by one.

## Packet ID table

The game registers 96 packet IDs in `Packet::staticCtor()`: 56 server-to-client, 14 client-to-server and 26 both ways. A packet arriving in a direction it is not registered for is dropped. IDs 150–167 are 4J additions and 201 is repurposed, so these have with no Java Edition equivalent.

| ID | Hex | Packet class | Direction |
| --- | --- | --- | --- |
| 0 | 0x00 | KeepAlivePacket | both |
| 1 | 0x01 | LoginPacket | both |
| 2 | 0x02 | PreLoginPacket | both |
| 3 | 0x03 | ChatPacket | both |
| 4 | 0x04 | SetTimePacket | S→C |
| 5 | 0x05 | SetEquippedItemPacket | S→C |
| 6 | 0x06 | SetSpawnPositionPacket | S→C |
| 7 | 0x07 | InteractPacket | C→S |
| 8 | 0x08 | SetHealthPacket | S→C |
| 9 | 0x09 | RespawnPacket | both |
| 10 | 0x0A | MovePlayerPacket | both |
| 11 | 0x0B | MovePlayerPacket.Pos | both |
| 12 | 0x0C | MovePlayerPacket.Rot | both |
| 13 | 0x0D | MovePlayerPacket.PosRot | both |
| 14 | 0x0E | PlayerActionPacket | C→S |
| 15 | 0x0F | UseItemPacket | C→S |
| 16 | 0x10 | SetCarriedItemPacket | both |
| 17 | 0x11 | EntityActionAtPositionPacket | S→C |
| 18 | 0x12 | AnimatePacket | both |
| 19 | 0x13 | PlayerCommandPacket | C→S |
| 20 | 0x14 | AddPlayerPacket | S→C |
| 22 | 0x16 | TakeItemEntityPacket | S→C |
| 23 | 0x17 | AddEntityPacket | S→C |
| 24 | 0x18 | AddMobPacket | S→C |
| 25 | 0x19 | AddPaintingPacket | S→C |
| 26 | 0x1A | AddExperienceOrbPacket | S→C |
| 27 | 0x1B | PlayerInputPacket | C→S |
| 28 | 0x1C | SetEntityMotionPacket | S→C |
| 29 | 0x1D | RemoveEntitiesPacket | S→C |
| 30 | 0x1E | MoveEntityPacket | S→C |
| 31 | 0x1F | MoveEntityPacket.Pos | S→C |
| 32 | 0x20 | MoveEntityPacket.Rot | S→C |
| 33 | 0x21 | MoveEntityPacket.PosRot | S→C |
| 34 | 0x22 | TeleportEntityPacket | S→C |
| 35 | 0x23 | RotateHeadPacket | S→C |
| 38 | 0x26 | EntityEventPacket | S→C |
| 39 | 0x27 | SetEntityLinkPacket | S→C |
| 40 | 0x28 | SetEntityDataPacket | S→C |
| 41 | 0x29 | UpdateMobEffectPacket | S→C |
| 42 | 0x2A | RemoveMobEffectPacket | S→C |
| 43 | 0x2B | SetExperiencePacket | S→C |
| 44 | 0x2C | UpdateAttributesPacket | S→C |
| 50 | 0x32 | ChunkVisibilityPacket | S→C |
| 51 | 0x33 | BlockRegionUpdatePacket | S→C |
| 52 | 0x34 | ChunkTilesUpdatePacket | S→C |
| 53 | 0x35 | TileUpdatePacket | S→C |
| 54 | 0x36 | TileEventPacket | S→C |
| 55 | 0x37 | TileDestructionPacket | S→C |
| 60 | 0x3C | ExplodePacket | S→C |
| 61 | 0x3D | LevelEventPacket | S→C |
| 62 | 0x3E | LevelSoundPacket | S→C |
| 63 | 0x3F | LevelParticlesPacket | S→C |
| 70 | 0x46 | GameEventPacket | S→C |
| 71 | 0x47 | AddGlobalEntityPacket | S→C |
| 100 | 0x64 | ContainerOpenPacket | S→C |
| 101 | 0x65 | ContainerClosePacket | both |
| 102 | 0x66 | ContainerClickPacket | C→S |
| 103 | 0x67 | ContainerSetSlotPacket | both |
| 104 | 0x68 | ContainerSetContentPacket | S→C |
| 105 | 0x69 | ContainerSetDataPacket | S→C |
| 106 | 0x6A | ContainerAckPacket | both |
| 107 | 0x6B | SetCreativeModeSlotPacket | both |
| 108 | 0x6C | ContainerButtonClickPacket | C→S |
| 130 | 0x82 | SignUpdatePacket | both |
| 131 | 0x83 | ComplexItemDataPacket | S→C |
| 132 | 0x84 | TileEntityDataPacket | S→C |
| 133 | 0x85 | TileEditorOpenPacket | S→C |
| 150 | 0x96 | CraftItemPacket | C→S |
| 151 | 0x97 | TradeItemPacket | C→S |
| 152 | 0x98 | DebugOptionsPacket | C→S |
| 153 | 0x99 | ServerSettingsChangedPacket | both |
| 154 | 0x9A | TexturePacket | both |
| 155 | 0x9B | ChunkVisibilityAreaPacket | S→C |
| 156 | 0x9C | UpdateProgressPacket | S→C |
| 157 | 0x9D | TextureChangePacket | both |
| 158 | 0x9E | UpdateGameRuleProgressPacket | S→C |
| 159 | 0x9F | KickPlayerPacket | C→S |
| 160 | 0xA0 | TextureAndGeometryPacket | both |
| 161 | 0xA1 | TextureAndGeometryChangePacket | both |
| 162 | 0xA2 | MoveEntityPacketSmall | S→C |
| 163 | 0xA3 | MoveEntityPacketSmall.Pos | S→C |
| 164 | 0xA4 | MoveEntityPacketSmall.Rot | S→C |
| 165 | 0xA5 | MoveEntityPacketSmall.PosRot | S→C |
| 166 | 0xA6 | XZPacket | both |
| 167 | 0xA7 | GameCommandPacket | C→S |
| 200 | 0xC8 | AwardStatPacket | S→C |
| 201 | 0xC9 | PlayerInfoPacket | both |
| 202 | 0xCA | PlayerAbilitiesPacket | both |
| 205 | 0xCD | ClientCommandPacket | C→S |
| 206 | 0xCE | SetObjectivePacket | S→C |
| 207 | 0xCF | SetScorePacket | S→C |
| 208 | 0xD0 | SetDisplayObjectivePacket | S→C |
| 209 | 0xD1 | SetPlayerTeamPacket | S→C |
| 250 | 0xFA | CustomPayloadPacket | both |
| 254 | 0xFE | GetInfoPacket | C→S |
| 255 | 0xFF | DisconnectPacket | both |

Direction comes from the `receiveOnClient` / `receiveOnServer` flags in each `map()` call. ID 103 is registered twice; the first registration (both ways) is the one that counts.

## Packet field layouts

Fields are listed in wire order, after the 1-byte packet ID. They come from each packet's `read()` and were cross-checked against its `write()`; the two agree for all 96 packets. The build defines `_LARGE_WORLDS`, so the large-world variant is shown wherever the code has two.

Notation: `i8`/`u8` byte, `i16` short, `i32` int, `i64` long, `f32` float, `f64` double, `bool`. `str(N)` = UTF-16 string, at most N code units. `mutf8` = Java `writeUTF` string (uint16 byte length + modified UTF-8). `item`, `nbt`, `meta` = the composite types under Transport. `uid` = PlayerUID (i64).

### Connection and login

| ID  | Packet                | Fields                                                                                                                                                                                                                                                                                                                                                                                                               |
| --- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0   | KeepAlive             | i32 id                                                                                                                                                                                                                                                                                                                                                                                                               |
| 1   | Login                 | i32 clientVersion (78 C→S) · str(20) userName · str(16) levelType (`""` = normal) · i64 seed · i32 gameType · i8 dimension · i8 mapHeight · i8 maxPlayers · uid offlineXuid · uid onlineXuid · bool friendsOnlyUGC · i32 ugcPlayersVersion · i8 difficulty · i32 multiplayerInstanceId · i8 playerIndex · i32 skinId · i32 capeId · bool isGuest · bool newSeaLevel · i32 gamePrivileges · i16 xzSize · u8 hellScale |
| 2   | PreLogin              | i16 netcodeVersion (560) · str(32) loginKey (name C→S, `"-"` S→C) · i8 friendsOnlyBits · i32 ugcPlayersVersion · u8 playerCount · playerCount × uid · 14 × i8 uniqueSaveName (ASCII) · i32 serverSettings · i8 hostIndex · i32 texturePackId                                                                                                                                                                         |
| 3   | Chat                  | i16 messageType · i16 packedCounts (bits 4–7 = string count, bits 0–3 = int count) · strings × str · ints × i32                                                                                                                                                                                                                                                                                                      |
| 153 | ServerSettingsChanged | u8 action · i32 data                                                                                                                                                                                                                                                                                                                                                                                                 |
| 159 | KickPlayer            | i8 networkSmallId                                                                                                                                                                                                                                                                                                                                                                                                    |
| 201 | PlayerInfo            | i8 networkSmallId · i16 colourIndex · i32 privileges · i32 entityId                                                                                                                                                                                                                                                                                                                                                  |
| 250 | CustomPayload         | str(20) channel · i16 length · length × u8 data                                                                                                                                                                                                                                                                                                                                                                      |
| 254 | GetInfo               | no fields (server replies Disconnect ServerFull)                                                                                                                                                                                                                                                                                                                                                                     |
| 255 | Disconnect            | i32 reason                                                                                                                                                                                                                                                                                                                                                                                                           |

Login is used in both directions with the same layout. The client fills in name, version, XUIDs, skin and cape. The server fills in the entity ID (sent in `clientVersion`'s slot), world settings and privileges. Chat `messageType` 0 is free text; other values are localised messages (bed, death, join/leave and so on) whose arguments are the strings and ints.

### Player state and movement

| ID | Packet | Fields |
| --- | --- | --- |
| 4 | SetTime | i64 gameTime · i64 dayTime |
| 6 | SetSpawnPosition | i32 x · i32 y · i32 z |
| 8 | SetHealth | f32 health · i16 food · f32 saturation · i8 damageSource |
| 9 | Respawn | i8 dimension · i8 gameType · i16 mapHeight · str(16) levelType · i64 seed · i8 difficulty · bool newSeaLevel · i16 newEntityId · i16 xzSize · u8 hellScale |
| 10 | MovePlayer | u8 flags (bit 0 onGround, bit 1 isFlying) |
| 11 | MovePlayer.Pos | f64 x · f64 y · f64 yView · f64 z · u8 flags |
| 12 | MovePlayer.Rot | f32 yRot · f32 xRot · u8 flags |
| 13 | MovePlayer.PosRot | f64 x · f64 y · f64 yView · f64 z · f32 yRot · f32 xRot · u8 flags |
| 14 | PlayerAction | u8 action · i32 x · u8 y · i32 z · u8 face |
| 15 | UseItem | i32 x · u8 y · i32 z · u8 face · item · u8 clickX · u8 clickY · u8 clickZ (each ÷ 16 = position within the block) |
| 16 | SetCarriedItem | i16 slot |
| 18 | Animate | i32 entityId · i8 action |
| 19 | PlayerCommand | i32 entityId · i8 action · i32 data |
| 27 | PlayerInput | f32 strafe · f32 forward · bool jumping · bool sneaking |
| 43 | SetExperience | f32 progress · i16 level · i16 total |
| 70 | GameEvent | i8 event · i8 param |
| 202 | PlayerAbilities | i8 flags (1 invulnerable, 2 flying, 4 canFly, 8 instabuild) · f32 flySpeed · f32 walkSpeed |
| 205 | ClientCommand | i8 action |

MovePlayer `y` and `yView` swap meaning by direction, as in Java Edition. C→S: `y` = feet (bounding-box bottom), `yView` = eye height. S→C teleport: `y` = feet + 1.62, `yView` = feet. While riding, the client sends PosRot with `y` = `yView` = −999 and puts its movement input in `x` and `z`.

### Entities

Entity positions are fixed-point blocks × 32. Angles are bytes of 256ths of a turn (degrees × 256 / 360). Velocities are blocks per tick × 8000. Packets marked *id11* pack an 11-bit entity ID (0–2047) into the low bits of an i16.

| ID | Packet | Fields |
| --- | --- | --- |
| 5 | SetEquippedItem | i32 entityId · i16 slot · item |
| 7 | Interact | i32 sourceId · i32 targetId · i8 action |
| 17 | EntityActionAtPosition | i32 entityId · i8 action · i32 x · i8 y · i32 z |
| 20 | AddPlayer | i32 entityId · str(20) name · i32 x · i32 y · i32 z · i8 yRot · i8 xRot · i8 yHeadRot · i16 carriedItem · uid xuid · uid onlineXuid · i8 playerIndex · i32 skinId · i32 capeId · i32 privileges · meta |
| 22 | TakeItemEntity | i32 itemEntityId · i32 playerId |
| 23 | AddEntity | i16 entityId · i8 type · i32 x · i32 y · i32 z · i8 yRot · i8 xRot · i32 data · if data > −1: i16 xa · i16 ya · i16 za |
| 24 | AddMob | i16 entityId · u8 type · i32 x · i32 y · i32 z · i8 yRot · i8 xRot · i8 yHeadRot · i16 xd · i16 yd · i16 zd · meta |
| 25 | AddPainting | i32 entityId · str motive · i32 x · i32 y · i32 z · i32 direction |
| 26 | AddExperienceOrb | i32 entityId · i32 x · i32 y · i32 z · i16 value |
| 28 | SetEntityMotion | i16 idAndFlag (*id11*; bit 11 set = byte mode) · byte mode: 3 × i8 (× 16 to get the i16 value), else 3 × i16 xa, ya, za |
| 29 | RemoveEntities | i8 count · count × i32 entityId |
| 30 | MoveEntity | i16 entityId |
| 31 | MoveEntity.Pos | i16 entityId · i8 dx · i8 dy · i8 dz |
| 32 | MoveEntity.Rot | i16 entityId · i8 yRot · i8 xRot |
| 33 | MoveEntity.PosRot | i16 entityId · i8 dx · i8 dy · i8 dz · i8 yRot · i8 xRot |
| 34 | TeleportEntity | i16 entityId · i32 x · i32 y · i32 z · i8 yRot · i8 xRot |
| 35 | RotateHead | i32 entityId · i8 yHeadRot |
| 38 | EntityEvent | i32 entityId · i8 eventId |
| 39 | SetEntityLink | i32 sourceId · i32 destId · u8 type |
| 40 | SetEntityData | i32 entityId · meta |
| 41 | UpdateMobEffect | i32 entityId · i8 effectId · i8 amplifier · i16 durationTicks |
| 42 | RemoveMobEffect | i32 entityId · i8 effectId |
| 44 | UpdateAttributes | i32 entityId · i32 count · count × (i16 attributeId · f64 base · i16 modCount · modCount × (i32 modifierId · f64 amount · i8 operation)) |
| 71 | AddGlobalEntity | i32 entityId · i8 type (lightning) · i32 x · i32 y · i32 z |
| 162 | MoveEntitySmall | i16 entityId |
| 163 | MoveEntitySmall.Pos | i16 *id11* + dy in bits 11–15 (signed) · i8: dx in high 4 bits, dz in low 4 bits (both signed) |
| 164 | MoveEntitySmall.Rot | i16 *id11* + yRot in bits 11–15 (signed) |
| 165 | MoveEntitySmall.PosRot | i16 *id11* + yRot in bits 11–15 · i16: dx bits 11–15, dy bits 5–10, dz bits 0–4 (all signed) |

Attribute and modifier IDs are 4J enums (`eATTRIBUTE_ID`, `eMODIFIER_ID`), not Java's string names and UUIDs. The Small move packets (162–165) are 4J bandwidth savers that the server uses instead of 30–33 when the deltas fit.

### World and chunks

| ID | Packet | Fields |
| --- | --- | --- |
| 50 | ChunkVisibility | i32 chunkX · i32 chunkZ · u8 visible |
| 51 | BlockRegionUpdate | i8 flags (1 = full chunk, 2 = zero height) · i32 x · i16 y · i32 z · u8 xs−1 · u8 ys−1 · u8 zs−1 · i32 sizeAndLevel (bits 30–31 = level index 0 Overworld / 1 Nether / 2 End, bits 0–29 = byte count) · that many compressed bytes |
| 52 | ChunkTilesUpdate | i16 chunkX · i16 chunkZ · i8 countAndFlags (bit 7 = all data 0, bits 5–6 = level, bits 0–4 = count) · count × (i16 xz, where bit 7 set = new block ID follows · i8 y · \[u8 blockId\] · \[u8 data unless all-zero\]) |
| 53 | TileUpdate | i32 x · u8 y · i32 z · i16 blockId · u8 dataAndLevel (low 4 bits data, high 4 bits level) |
| 54 | TileEvent | i32 x · i16 y · i32 z · u8 b0 · u8 b1 · i16 blockId |
| 55 | TileDestruction | i32 entityId · i32 x · i32 y · i32 z · u8 stage |
| 60 | Explode | bool knockbackOnly · unless knockbackOnly: f64 x · f64 y · f64 z · f32 radius · i32 count · count × (i8 dx · i8 dy · i8 dz) · then always f32 knockbackX · f32 knockbackY · f32 knockbackZ |
| 61 | LevelEvent | i32 type · i32 x · u8 y · i32 z · i32 data · bool global |
| 62 | LevelSound | i32 soundId · i32 x · i32 y · i32 z · f32 volume · f32 pitch |
| 63 | LevelParticles | str(64) name · f32 x · f32 y · f32 z · f32 xDist · f32 yDist · f32 zDist · f32 speed · i32 count |
| 155 | ChunkVisibilityArea | i32 minX · i32 maxX · i32 minZ · i32 maxZ |
| 166 | XZ | u8 action (stronghold location, …) · i32 x · i32 z |

**Chunk payload (51).** The compressed bytes are a zlib stream (standard `compress`/`uncompress`) wrapped around 4J's RLE. In the RLE, a byte 0–254 is a literal. `0xFF n` with n = 0–2 means n + 1 bytes of `0xFF`. `0xFF n b` with n ≥ 3 means n + 1 copies of byte b. Decompressed, the region holds xs·ys·zs block IDs (index `y·xs·zs + z·xs + x`), then three nibble arrays (block data, block light, sky light) of xs·ys·zs / 2 bytes each, then 256 biome bytes if it is a full chunk. For full chunks, `ys` is trimmed to the highest non-empty block, and the nibble arrays are written as a lower part (y < 128) followed by an upper part.

### Containers and crafting

| ID | Packet | Fields |
| --- | --- | --- |
| 100 | ContainerOpen | u8 windowId · u8 type · u8 size · bool hasCustomName · if type = 11 (horse): i32 entityId · if hasCustomName: str(64) title |
| 101 | ContainerClose | i8 windowId |
| 102 | ContainerClick | i8 windowId · i16 slot · i8 button · i16 actionUid · i8 clickType · item |
| 103 | ContainerSetSlot | i8 windowId (−1 = cursor) · i16 slot · item |
| 104 | ContainerSetContent | i8 windowId · i16 count (0–256) · count × item |
| 105 | ContainerSetData | i8 windowId · i16 property · i16 value |
| 106 | ContainerAck | i8 windowId · i16 actionUid · u8 accepted |
| 107 | SetCreativeModeSlot | i16 slot · item |
| 108 | ContainerButtonClick | i8 windowId · i8 buttonId |
| 150 | CraftItem | i16 actionUid · i32 recipeIndex |
| 151 | TradeItem | i32 windowId · i32 offerIndex |

Crafting is 4J's own: the console crafting menu sends CraftItem (150) with a recipe index instead of Java's slot clicks in a crafting grid.

### Tile entities, signs and maps

| ID | Packet | Fields |
| --- | --- | --- |
| 130 | SignUpdate | i32 x · i16 y · i32 z · bool verified · bool censored · 4 × str line |
| 131 | ComplexItemData | i16 itemType · i16 itemId · u16 length · length × u8 data (map pixels) |
| 132 | TileEntityData | i32 x · i16 y · i32 z · i8 type · nbt |
| 133 | TileEditorOpen | i8 editorType · i32 x · i32 y · i32 z |

### Skins, textures and 4J-specific

| ID | Packet | Fields |
| --- | --- | --- |
| 152 | DebugOptions | i32 flags |
| 154 | Texture | mutf8 textureName · i16 byteCount (≤ 0 = request, nothing follows) · byteCount × u8 texture file |
| 156 | UpdateProgress | i8 percentage |
| 157 | TextureChange | i32 entityId · i8 changeType · mutf8 path |
| 158 | UpdateGameRuleProgress | i32 ruleType · str(64) messageId · i32 icon · i8 auxValue · i32 dataTag · i32 length · length × u8 data |
| 160 | TextureAndGeometry | mutf8 textureName · i32 skinId · i16 byteCount · byteCount × u8 texture file · i32 animOverrideBits · i16 boxCount (0–256) · boxCount × (i16 bodyPart · 8 × f32 x, y, z, h, w, d, u, v) |
| 161 | TextureAndGeometryChange | i32 entityId · i32 skinId · mutf8 path |
| 167 | GameCommand | i32 command · i16 length · length × u8 data |
| 200 | AwardStat | i32 statId · i32 length · length × u8 data |

The skin packets are a request/reply pair. A side that lacks a custom skin sends the packet with byteCount 0, and the owner replies with the same packet carrying the file (1–32,767 bytes, since the count is a signed i16). The server answers from its cache, or queues the request until it has the skin. These are the only packets that use `mutf8` strings.

### Scoreboard

| ID | Packet | Fields |
| --- | --- | --- |
| 206 | SetObjective | str(16) name · str(32) displayName · i8 method (0 add, 1 remove, 2 change) |
| 207 | SetScore | str(20) owner · i8 method (0 change, 1 remove) · unless remove: str(16) objective · i32 score |
| 208 | SetDisplayObjective | i8 slot · str(16) objective |
| 209 | SetPlayerTeam | str(16) name · i8 method (0 add, 1 remove, 2 change, 3 join, 4 leave) · if add/change: str(32) displayName · str(16) prefix · str(16) suffix · i8 options · if add/join/leave: i16 count · count × str(20) player |

## Implementation notes for a Python server

The pieces most likely to trip up a clean-room server are the unframed packet stream, UTF-16 strings, uncompressed NBT and the zlib + RLE chunk codec. Everything else is Java 1.6-style big-endian fields.

- **Parse a stream, not frames.** Strip each 4-byte length header and append the payload to one buffer per connection. Then decode as many whole packets as the buffer holds, and keep the remainder for the next frame. `struct.unpack('>i', …)` and friends cover every primitive.
- **Send the smallId byte first.** A client that receives a framed packet before its smallId byte misreads everything after it. Hand out IDs from 4 upward: 0–3 are reserved for local split-screen players (`XUSER_MAX_COUNT`).
- **Strings are UTF-16BE**, length-prefixed in code units. Use `s.encode('utf-16-be')` with `len(s.encode('utf-16-be')) // 2` as the length, not `len(s)`, so characters outside the BMP count as two. Only the skin packets (154, 157, 160, 161) use Java modified UTF-8.
- **Never gzip NBT.** Item and tile-entity NBT goes on the wire raw, behind an i16 length.
- **Chunk codec in Python:** `zlib.compress(rle_encode(raw))` and the reverse. An RLE encoder that never emits runs (`0xFF` → `FF 00`, other bytes as literals) is valid and lets you start before writing the run-length logic.
- **Unknown packet = dead connection.** With no per-packet length, a server that does not implement an ID the client sends cannot skip it. Implement the `read` side of every C→S and both-ways packet (40 in total) before connecting a real client, even if the handler is empty.
- **Version numbers to send:** netcodeVersion 560 in PreLogin, protocol 78 in Login.
- **Expect KeepAlive** from the client every second, and send your own. The reference server drops a login that does not finish within 30 s (600 ticks); a Python server can pick its own limit.

### Source files

All paths are under `minecraft-console/`.

| Topic | File |
| --- | --- |
| Packet registry and string, item and NBT codecs | `Minecraft.World/Packet.cpp` |
| One packet's fields | `Minecraft.World/<Name>Packet.cpp`, `read()` and `write()` |
| TCP framing, smallId, LAN broadcast | `Minecraft.Client/Windows64/Network/WinsockNetLayer.cpp` / `.h` |
| Send buffering, KeepAlive and timeouts | `Minecraft.World/Connection.cpp` |
| Login checks | `Minecraft.Client/PendingConnection.cpp` |
| Join sequence | `Minecraft.Client/PlayerList.cpp`, `placeNewPlayer()` |
| In-game C→S handlers | `Minecraft.Client/PlayerConnection.cpp` |
| Chunk compression | `Minecraft.World/compression.cpp` |
| Entity metadata | `Minecraft.World/SynchedEntityData.cpp` |

### Open questions

- [ ] Confirm that the 360 Revived client uses netcodeVersion 560 (instead of 495) and the same packet set. Its source is not public, so this needs a capture of a real 360 Revived login.
- [ ] Map the nibble order inside the chunk payload's data and light arrays (`SparseDataStorage::getDataRegion`, `SparseLightStorage::getDataRegion`).
- [ ] List the enums referenced but not expanded here: Chat message types, GameEvent IDs, PlayerAction actions, container types, attribute IDs.
