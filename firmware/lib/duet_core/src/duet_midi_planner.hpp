// The optional planner module, installed in the device API (Api::install_planner) by a
// board built with DUET_PLANNER: an uploaded MIDI file read (duet_midi.hpp), planned
// (duet_planner.hpp) and stored as a song, with no server.
#pragma once
#include "duet_api.hpp"
#include "duet_device.hpp"
#include "duet_instruments.hpp"

namespace duet {

class MidiPlanner : public Planner {
 public:
  MidiPlanner(Device& device, const CarriageInstrument& robot,
              const KeyboardInstrument& keyboard, const Channels& channels)
      : device_(device), robot_(robot), keyboard_(keyboard), channels_(channels) {}

  Response plan_midi(const std::vector<uint8_t>& midi, const std::string& title,
                     int slot) override;

 private:
  Device& device_;
  const CarriageInstrument& robot_;
  const KeyboardInstrument& keyboard_;
  Channels channels_;
};

}  // namespace duet
