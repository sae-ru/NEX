#pragma once
#include <cstdint>
namespace nexrt {
// Compiler-private request numbers, shared with verified MLIR generation.
enum class TaskRequestKind:int64_t {
  Yield,WithTasks,Spawn,Wait,ChannelNew,Send,Receive,Close,Cancel,CurrentScope,
  FileReadText,FileReadBytes
};
inline constexpr int64_t taskCodeABI=INT64_C(0x4e45585400000002);
// Actual checked declaration/image requirements, never filesystem authority.
inline constexpr int64_t taskCodeDeclaredTask=1,taskCodeServer=2,taskCodeDeclaredFs=4,
  taskCodeFileRead=8,taskCodeImageFileRead=16,taskCodeRequirementsMask=31;
}
