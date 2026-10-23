#pragma once
#include "nex/language.h"
#include <limits>
#include <optional>

namespace nex {
using TaskSlotId=uint32_t;
inline constexpr TaskSlotId noTaskSlot=std::numeric_limits<TaskSlotId>::max();
struct TaskSlot {Type type;std::string name;Span span;bool temporary=true;};
struct TaskInstruction {
  enum Kind { Eval,Copy,Drop,Jump,Branch,Pattern,Pause,Call,Return,Fail,Poll } kind=Fail;
  Span span;const void *source=nullptr;
  TaskSlotId output=noTaskSlot;
  std::vector<TaskSlotId> inputs,bindings;
  size_t yes=0,no=0;
  E atom;P pattern;
  std::string operation;
  bool indirect=false,propagatedError=false;
};
// Optional source debugger metadata. It never adds execution instructions or
// changes continuation PCs. Binding IDs and point indices are separate from
// slots and PCs; a point exposes initialized lexical bindings only.
struct TaskDebugBindingIR {
  uint32_t id=0,scope=0,depth=0;
  TaskSlotId slot=noTaskSlot;
  std::string name;Type type;Span span;
  bool opaque=false;
};
struct TaskDebugPointIR {
  enum Kind {Entry=0,Statement=1,Loop=2,Call=3,Resume=4,Return=5} kind=Statement;
  size_t pc=0;Span span;const void *source=nullptr;
  std::vector<uint32_t> visible;
};
struct TaskDebugIR {
  std::vector<TaskDebugBindingIR> bindings;
  std::vector<TaskDebugPointIR> points;
};
struct TaskFunctionIR {
  std::string name;Type result;
  std::vector<TaskSlot> slots;
  std::vector<TaskSlotId> parameters,captures;
  std::vector<TaskInstruction> code;
  std::optional<TaskDebugIR> debug;
};
// Private checked-source lowering. Slots contain owned Values, never raw native
// Handles. Pure atoms have only slot-reference children. Suspension/calls are
// explicit boundaries; branch arms, loop state and lexical cleanup survive them.
TaskFunctionIR lowerTaskFunction(const Program &,const Function &,bool liftPure=false,bool debugMetadata=false);
// Exact checked-source metadata shared with the out-of-process watch validator.
// File is the immutable DWARF source anchor. The caller adds its code site ID.
llvm::json::Object taskDebugFunctionMetadata(const Program &,const Function &,const TaskFunctionIR &,const std::string &file);
llvm::json::Object taskDebugFunctionMetadata(const Program &,const Function &,const std::string &file);
std::string taskSlotName(TaskSlotId);
void validateTaskIR(const TaskFunctionIR &);
}
