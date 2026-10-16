#pragma once
#include "nex_value.h"
namespace nexrt {
std::string encodeJSON(const Value &value);
Value decodeJSON(const std::string &text,const std::string &schema);
}
