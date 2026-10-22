#pragma once
#include <cstdint>
namespace nexrt {
// Compiler-private request numbers, shared with verified MLIR generation.
enum class TaskRequestKind:int64_t {
  Yield,WithTasks,Spawn,Wait,ChannelNew,Send,Receive,Close,Cancel,CurrentScope
};
}
