#pragma once
#include "nex/language.h"

namespace nex {
// A private, pre-emission authority-flow pass. It diagnoses statically known
// escapes; unknown calls, joins and channel payloads retain runtime obligations.
// It is deliberately separate from check(): runtime conformance fixtures must
// also be able to exercise invalid transfers, and public018 has no task mode.
struct TaskLifetimeReport {
  uint64_t functions=0,regions=0,transfers=0,proved=0,dynamic=0;
  uint64_t opaqueCalls=0,widenings=0,steps=0;
  // Private exception-flow counters; existing public serializers stay unchanged.
  uint64_t handlers=0,exceptionalEdges=0,exceptionalJoins=0;
};
TaskLifetimeReport analyzeTaskLifetimes(const Program &program,
    const std::string &entry="",uint64_t analysisLimit=262144);
}
