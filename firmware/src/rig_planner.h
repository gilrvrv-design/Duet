// The optional planner module for this rig (DUET_PLANNER): its carriage instrument and
// keyboard, compiled in from the Hub's instrument files. A rig whose instruments are not
// compiled in does not build.
#pragma once
#include "duet_instrument_data.hpp"
#include "duet_midi_planner.hpp"
#include "rig.h"

constexpr int kRigRobot = duet::instrument_index(duet::kCarriageInstruments, PROFILE_ID);
constexpr int kRigKeyboard = duet::instrument_index(duet::kKeyboardInstruments, KEYBOARD_ID);
static_assert(kRigRobot >= 0, "the rig's carriage instrument is not compiled in");
static_assert(kRigKeyboard >= 0, "the rig's keyboard is not compiled in");

inline duet::MidiPlanner rig_planner(duet::Device& device, const duet::Channels& channels) {
  return duet::MidiPlanner(device, duet::kCarriageInstruments[kRigRobot],
                           duet::kKeyboardInstruments[kRigKeyboard], channels);
}
