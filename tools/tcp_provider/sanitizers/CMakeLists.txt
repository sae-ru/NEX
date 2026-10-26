cmake_minimum_required(VERSION 3.25)
project(NEXTypedTCPHost LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Threads REQUIRED)
find_package(OpenSSL REQUIRED)
if(NOT IS_DIRECTORY "${NEX_SOURCE}/runtime")
  message(FATAL_ERROR "NEX_SOURCE must select the exact frozen runtime")
endif()
add_executable(tcp_typed_host host.cpp
 "${NEX_SOURCE}/runtime/nex_foreign.cpp"
 "${NEX_SOURCE}/runtime/foreign_runtime.cpp"
 "${NEX_SOURCE}/runtime/runtime.cpp"
 "${NEX_SOURCE}/runtime/nex_ffi_loader.cpp"
 "${NEX_SOURCE}/runtime/nex_ffi.cpp"
 "${NEX_SOURCE}/runtime/nex_ffi_types.cpp"
 "${NEX_SOURCE}/runtime/nex_ffi_resources.cpp"
 "${NEX_SOURCE}/runtime/nex_external_resource.cpp"
 "${NEX_SOURCE}/runtime/nex_resource_region.cpp"
 "${NEX_SOURCE}/runtime/nex_resource_executor.cpp"
 "${NEX_SOURCE}/runtime/nex_files.cpp"
 "${NEX_SOURCE}/runtime/nex_json.cpp"
 "${NEX_SOURCE}/runtime/nex_task_external.cpp")
target_include_directories(tcp_typed_host PRIVATE "${NEX_SOURCE}/runtime")
target_compile_options(tcp_typed_host PRIVATE -Wall -Wextra -Wpedantic -fno-omit-frame-pointer)
target_link_libraries(tcp_typed_host PRIVATE Threads::Threads OpenSSL::Crypto ${CMAKE_DL_LIBS})
