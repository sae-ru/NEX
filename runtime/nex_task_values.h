#pragma once
#include "nex_tasks.h"
namespace nexrt {
// Genuine owned payloads. The scope/ticket/channel identities hold weak group
// ownership; copying a Value cannot extend a lexical scope's authority.
struct TaskData final:Data {
  const TaskGroup::Scope scope;
  const TaskGroup::Ticket ticket;
  const TaskGroup::Channel channel;
  const int64_t payloadKind;
private:
  friend struct TaskValueAccess;
  TaskData(TaskGroup::Scope scope,TaskGroup::Ticket ticket,TaskGroup::Channel channel,
           Kind kind,int64_t payloadKind):Data(kind,sizeof(TaskData)),scope(scope),
           ticket(ticket),channel(channel),payloadKind(payloadKind){}
};
const TaskData &taskData(const Value &,Data::Kind);
Value taskScopeValue(TaskGroup &,const TaskGroup::Scope &);
Value taskTicketValue(TaskGroup &,const TaskGroup::Ticket &,int64_t resultKind);
Value taskChannelValue(TaskGroup &,const TaskGroup::Channel &,int64_t payloadKind);
void validateTaskSnapshot(TaskGroup &,const Value &,const TaskGroup::Scope &target);
}
