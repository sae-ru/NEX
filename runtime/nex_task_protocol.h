#pragma once
#include <cstdint>
namespace nexrt {
// Compiler-private request numbers, shared with verified MLIR generation.
enum class TaskRequestKind:int64_t {
  Yield,WithTasks,Spawn,Wait,ChannelNew,Send,Receive,Close,Cancel,CurrentScope,
  FileReadText,FileReadBytes,Foreign,FileWriteText,FileWriteBytes,
  FileOpenRead,FileOpenWrite,FileOpenAppend,FileRead,FileWrite,FileSeek,FileSize,FileFlush,FileClose,FileIsOpen
};
inline constexpr int64_t taskCodeABI=INT64_C(0x4e45585400000003);
inline constexpr int64_t taskCodeWriteABI=INT64_C(0x4e45585400000004);
inline constexpr int64_t taskCodeStreamABI=INT64_C(0x4e45585400000005);
inline constexpr int64_t taskCodeFileStream=1024,taskCodeImageFileStream=2048,taskCodeStreamRequirementsMask=4095;
// Actual checked declaration/image requirements, never filesystem authority.
inline constexpr int64_t taskCodeDeclaredTask=1,taskCodeServer=2,taskCodeDeclaredFs=4,
  taskCodeFileRead=8,taskCodeImageFileRead=16,taskCodeDeclaredFfi=32,
  taskCodeForeign=64,taskCodeImageForeign=128,taskCodeRequirementsMask=255;
inline constexpr int64_t taskCodeFileWrite=256,taskCodeImageFileWrite=512,
  taskCodeWriteRequirementsMask=1023;
inline bool validTaskCodeRequirements(int64_t abi,int64_t requirements)noexcept{
  return abi==taskCodeABI?(requirements&~taskCodeRequirementsMask)==0:
    abi==taskCodeWriteABI?(requirements&~taskCodeWriteRequirementsMask)==0:
    abi==taskCodeStreamABI&&(requirements&~taskCodeStreamRequirementsMask)==0;
}
// Published ABI3 provider/capture records retain their task/fs-only prefix.
// Private standalone source FFI requirements do not widen that image contract.
inline constexpr int64_t taskProviderRequirementsMask=31;
// Explicit023 provider records exclude standalone source FFI requirements.
inline constexpr int64_t taskWriteProviderRequirementsMask=taskProviderRequirementsMask|taskCodeFileWrite|taskCodeImageFileWrite;
// ABI5 source-provider files remain distinct from C FFI/external authority.
inline constexpr int64_t taskStreamProviderRequirementsMask=taskWriteProviderRequirementsMask|taskCodeFileStream|taskCodeImageFileStream;
}
