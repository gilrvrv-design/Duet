// Who this device is, as it says in hello: the rig (rig.h) on the board it is built for
// (board.h, chosen by the build).
#pragma once
#include "board.h"
#include "duet_protocol.hpp"

constexpr duet::Identity IDENTITY{DEVICE_ID, BOARD, PROFILE_ID, FEATURES, BOARD_CHANNELS};
