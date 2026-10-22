#pragma once
#include "nex/language.h"
#include <limits>

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
struct TaskFunctionIR {
  std::string name;Type result;
  std::vector<TaskSlot> slots;
  std::vector<TaskSlotId> parameters,captures;
  std::vector<TaskInstruction> code;
};
// Private checked-source lowering. Slots contain owned Values, never raw native
// Handles. Pure atoms have only slot-reference children. Suspension/calls are
// explicit boundaries; branch arms, loop state and lexical cleanup survive them.
TaskFunctionIR lowerTaskFunction(const Program &,const Function &,bool liftPure=false);
std::string taskSlotName(TaskSlotId);
void validateTaskIR(const TaskFunctionIR &);
}
