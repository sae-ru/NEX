#pragma once
#include <cstddef>
#include <stdexcept>
#include <string>
#include <utility>
namespace nexrt {
struct DataError : std::runtime_error {
  std::string code;
  size_t offset=0;
  DataError(std::string code,std::string message,size_t offset=0)
      :std::runtime_error(std::move(message)),code(std::move(code)),offset(offset){}
};
}
