#pragma once
#include <cstddef>
#include <stdexcept>
#include <string>
#include <utility>
namespace nexrt {
struct DataError : std::runtime_error {
  std::string code,message;
  size_t offset=0;
  DataError(std::string code,std::string message,size_t offset=0)
      :std::runtime_error(""),code(std::move(code)),message(std::move(message)),offset(offset){}
  const char *what()const noexcept override{return message.c_str();}
};
}
