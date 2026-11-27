// Fixed-size queue of timed commands, always popped in time order (spec FR-D4).
// No heap allocation, so it is safe on the ESP32.
#pragma once
#include <cstddef>

#include "duet_protocol.hpp"

namespace duet {

template <size_t N>
class CommandQueue {
 public:
  bool push(const Command& c) {
    if (size_ == N) return false;
    size_t i = size_++;
    items_[i] = c;
    while (i > 0 && before(items_[i], items_[(i - 1) / 2])) {  // sift up
      swap(i, (i - 1) / 2);
      i = (i - 1) / 2;
    }
    return true;
  }

  bool empty() const { return size_ == 0; }
  size_t size() const { return size_; }
  const Command& top() const { return items_[0]; }

  Command pop() {
    Command out = items_[0];
    items_[0] = items_[--size_];
    size_t i = 0;
    for (;;) {  // sift down
      size_t l = 2 * i + 1, r = l + 1, m = i;
      if (l < size_ && before(items_[l], items_[m])) m = l;
      if (r < size_ && before(items_[r], items_[m])) m = r;
      if (m == i) break;
      swap(i, m);
      i = m;
    }
    return out;
  }

  void clear() { size_ = 0; }

 private:
  static bool before(const Command& a, const Command& b) {
    return a.t_us < b.t_us || (a.t_us == b.t_us && a.seq < b.seq);
  }
  void swap(size_t a, size_t b) {
    Command t = items_[a];
    items_[a] = items_[b];
    items_[b] = t;
  }

  Command items_[N];
  size_t size_ = 0;
};

}  // namespace duet
