#pragma once
#include "nex_resource.h"
#include "nex_task_external.h"
#include <chrono>
#include <span>

namespace nexrt {
// Private trusted-host transport. Endpoint names are operator-selected and map
// to exact numeric addresses/ports. No source metadata or worker TLS grants IO.
struct TaskTcpEndpoint {std::string name,address;uint16_t port=0;};
struct TaskNetworkStats {size_t opened=0,closed=0,live=0,maximumLive=0;};
namespace task_network_detail {struct Grant;struct Exchange;}
class PreparedTaskTcpExchange;
class TaskNetworkGrant {
  std::shared_ptr<const task_network_detail::Grant> grant;
  friend class PreparedTaskTcpExchange;
public:
  TaskNetworkGrant()=default;
  TaskNetworkGrant(ResourceAccess,std::span<const TaskTcpEndpoint>);
  void check()const;
  TaskNetworkStats stats()const noexcept;
};
class PreparedTaskTcpExchange {
  std::shared_ptr<const task_network_detail::Exchange> exchange;
public:
  static constexpr size_t maximumInput=1024*1024,maximumReply=1024*1024;
  static constexpr unsigned maximumTimeoutMs=30000;
  // One request, write-side EOF, then a bounded reply through peer EOF. Queue
  // time counts toward this deadline; parent control can impose an earlier one.
  PreparedTaskTcpExchange(const TaskNetworkGrant &,const std::string &endpoint,
      std::span<const uint8_t> input,size_t replyLimit,unsigned timeoutMs=5000);
  size_t reservation()const noexcept;
  std::shared_ptr<TaskExternalOperation> operation()const;
  // Coordinator admission checks retained authority again after physical IO.
  // It returns raw host data; no source Value is constructed on an IO worker.
  TaskExternalResult admit(TaskExternalResult,const TaskExternalControl &control=TaskExternalControl{})const;
};
}
