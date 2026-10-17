#pragma once
#include "nex_value.h"
namespace nexrt {
void validateJSONText(const std::string &text);
std::string encodeJSON(const Value &value);
Value decodeJSON(const std::string &text,const std::string &schema);
}
