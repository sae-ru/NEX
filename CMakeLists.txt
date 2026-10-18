cmake_minimum_required(VERSION 3.25)
project(NEX VERSION 0.33.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT LLVM_DIR AND EXISTS "/opt/homebrew/opt/llvm@22/lib/cmake/llvm")
  set(LLVM_DIR "/opt/homebrew/opt/llvm@22/lib/cmake/llvm")
endif()
find_package(LLVM 22.1.0 REQUIRED CONFIG)
find_package(MLIR REQUIRED CONFIG HINTS "${LLVM_INSTALL_PREFIX}/lib/cmake/mlir")
find_package(SQLite3 REQUIRED)
if(NOT OPENSSL_ROOT_DIR AND EXISTS "/opt/homebrew/opt/openssl@3")
  set(OPENSSL_ROOT_DIR "/opt/homebrew/opt/openssl@3")
endif()
find_package(OpenSSL 3 REQUIRED)
set(NEX_Z3_ROOT "" CACHE PATH "Z3 development installation prefix")
if(APPLE AND NOT NEX_Z3_ROOT AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/build/deps/z3-5.3.1-arm64-osx-13.3")
  set(NEX_Z3_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/build/deps/z3-5.3.1-arm64-osx-13.3")
endif()
find_path(NEX_Z3_INCLUDE z3++.h HINTS "${NEX_Z3_ROOT}/include" REQUIRED)
find_library(NEX_Z3_LIBRARY NAMES z3 libz3 HINTS "${NEX_Z3_ROOT}/lib" "${NEX_Z3_ROOT}/bin" REQUIRED)
find_program(NEX_Z3_EXECUTABLE z3 HINTS "${NEX_Z3_ROOT}/bin")
get_filename_component(NEX_Z3_LIBRARY_DIR "${NEX_Z3_LIBRARY}" DIRECTORY)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
message(STATUS "NEX uses LLVM ${LLVM_PACKAGE_VERSION} and MLIR at ${MLIR_DIR}")

file(GLOB_RECURSE NEX_COMPILER_FILES CONFIGURE_DEPENDS "src/*.cpp" "include/*.h" "runtime/*.cpp" "runtime/*.h" "runtime/*.hpp")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${NEX_COMPILER_FILES})
set(NEX_BUILD_INPUTS "${PROJECT_VERSION};${LLVM_PACKAGE_VERSION};${CMAKE_CXX_COMPILER_ID};${CMAKE_CXX_COMPILER_VERSION};${CMAKE_BUILD_TYPE}")
foreach(NEX_INPUT IN LISTS NEX_COMPILER_FILES)
  file(SHA256 "${NEX_INPUT}" NEX_INPUT_HASH)
  string(APPEND NEX_BUILD_INPUTS ";${NEX_INPUT_HASH}")
endforeach()
string(SHA256 NEX_BUILD_ID "${NEX_BUILD_INPUTS}")

add_library(nex_frontend src/language.cpp src/generics.cpp src/matching.cpp src/interpreter.cpp src/watch_values.cpp src/debug_values.cpp src/operations.cpp src/modules.cpp src/wire_schema.cpp runtime/nex_json.cpp runtime/nex_store.cpp runtime/nex_files.cpp)
target_include_directories(nex_frontend PUBLIC include)
target_include_directories(nex_frontend PRIVATE runtime)
target_include_directories(nex_frontend SYSTEM PUBLIC ${LLVM_INCLUDE_DIRS})
target_link_libraries(nex_frontend PUBLIC LLVM SQLite::SQLite3)
target_compile_definitions(nex_frontend PRIVATE NEX_RESOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_options(nex_frontend PRIVATE -Wall -Wextra -Wpedantic)
add_executable(nex src/main.cpp src/backend.cpp src/native_toolchain.cpp src/debugging.cpp src/incremental.cpp src/profiling.cpp src/verification.cpp src/tasks.cpp src/task_process.cpp src/project.cpp src/operation_store.cpp src/typescript.cpp src/web.cpp src/api.cpp src/packaging.cpp)
target_include_directories(nex PRIVATE runtime)
target_include_directories(nex SYSTEM PRIVATE ${MLIR_INCLUDE_DIRS})
target_include_directories(nex SYSTEM PRIVATE ${NEX_Z3_INCLUDE})
target_link_libraries(nex PRIVATE nex_frontend MLIR SQLite::SQLite3 ${NEX_Z3_LIBRARY})
target_compile_options(nex PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(nex PRIVATE
  NEX_VERSION="${PROJECT_VERSION}"
  NEX_BUILD_ID="${NEX_BUILD_ID}"
  NEX_RUNTIME_SOURCE="${CMAKE_CURRENT_SOURCE_DIR}/runtime/runtime.cpp"
  NEX_LLVM_TOOLS="${LLVM_TOOLS_BINARY_DIR}"
  NEX_CLANG="${LLVM_TOOLS_BINARY_DIR}/clang++")
target_compile_definitions(nex PRIVATE NEX_SQLITE_INCLUDE="${SQLite3_INCLUDE_DIRS}" NEX_SQLITE_LIBRARY="${SQLite3_LIBRARIES}")
target_compile_definitions(nex PRIVATE NEX_OPENSSL_INCLUDE="${OPENSSL_INCLUDE_DIR}" NEX_OPENSSL_SSL="${OPENSSL_SSL_LIBRARY}" NEX_OPENSSL_CRYPTO="${OPENSSL_CRYPTO_LIBRARY}")
set_target_properties(nex PROPERTIES BUILD_RPATH "${LLVM_LIBRARY_DIRS};${NEX_Z3_LIBRARY_DIR}" INSTALL_RPATH "${LLVM_LIBRARY_DIRS};${NEX_Z3_LIBRARY_DIR}")
install(TARGETS nex RUNTIME DESTINATION bin)
install(DIRECTORY docs llm runtime examples lib web debug DESTINATION share/nex
  PATTERN node_modules EXCLUDE PATTERN test-results EXCLUDE PATTERN playwright-report EXCLUDE
  PATTERN .nex EXCLUDE PATTERN generated EXCLUDE PATTERN __pycache__ EXCLUDE)
install(FILES AGENTS.md README.md STATUS.md PLAN.md THIRD_PARTY.md DESTINATION share/nex)
install(DIRECTORY tools/linux DESTINATION share/nex/tools)
install(FILES tools/sdk_acceptance.py DESTINATION share/nex/tools)
install(FILES tools/sdk_bundle.py DESTINATION share/nex/tools)
install(FILES tools/app_bundle.py DESTINATION share/nex/tools)
install(FILES tools/application_acceptance.py DESTINATION share/nex/tools)
enable_testing()
add_test(NAME packaging COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/packaging.py $<TARGET_FILE:nex>)
find_package(Threads REQUIRED)
add_executable(nex_bytes_runtime_probe tests/bytes_runtime.cpp)
target_include_directories(nex_bytes_runtime_probe PRIVATE runtime)
target_compile_options(nex_bytes_runtime_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME bytes_runtime_native COMMAND nex_bytes_runtime_probe)
add_executable(nex_bytes_values_probe tests/bytes_values.cpp runtime/runtime.cpp runtime/nex_json.cpp runtime/nex_files.cpp runtime/files_runtime.cpp)
target_include_directories(nex_bytes_values_probe PRIVATE runtime)
target_compile_definitions(nex_bytes_values_probe PRIVATE NEX_PROFILE_ENABLED)
target_compile_options(nex_bytes_values_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_bytes_values_probe PRIVATE Threads::Threads)
add_test(NAME bytes_values_native COMMAND nex_bytes_values_probe)
add_executable(nex_files_runtime_probe tests/files_runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_files_runtime_probe PRIVATE runtime)
target_compile_options(nex_files_runtime_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_files_runtime_probe PRIVATE Threads::Threads)
add_test(NAME files_runtime_native COMMAND nex_files_runtime_probe)
add_test(NAME files COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/files.py $<TARGET_FILE:nex>)
add_executable(nex_float_runtime_probe tests/float_runtime.cpp runtime/runtime.cpp runtime/nex_json.cpp)
target_include_directories(nex_float_runtime_probe PRIVATE runtime)
target_link_libraries(nex_float_runtime_probe PRIVATE Threads::Threads)
add_test(NAME float_runtime_native COMMAND nex_float_runtime_probe --self-test)
add_test(NAME integration COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration.py $<TARGET_FILE:nex>)
add_test(NAME modules COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/modules.py $<TARGET_FILE:nex>)
add_test(NAME results COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/results.py $<TARGET_FILE:nex>)
add_test(NAME storage COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/storage.py $<TARGET_FILE:nex>)
add_test(NAME http COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/server_http.py $<TARGET_FILE:nex>)
add_test(NAME api COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/api_contracts.py $<TARGET_FILE:nex>)
add_test(NAME debugging COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/debugging.py $<TARGET_FILE:nex>)
add_test(NAME expressions COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/expressions.py $<TARGET_FILE:nex>)
add_test(NAME operations COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/operations.py $<TARGET_FILE:nex>)
add_test(NAME dap_transport COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/dap_transport.py $<TARGET_FILE:nex>)
add_test(NAME incremental COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/incremental.py $<TARGET_FILE:nex>)
add_test(NAME native_targets COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_targets.py $<TARGET_FILE:nex>)
add_test(NAME sdk_host COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/sdk_host.py $<TARGET_FILE:nex>)
add_test(NAME profiling COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/profiling.py $<TARGET_FILE:nex>)
add_test(NAME verification COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/verification.py $<TARGET_FILE:nex>)
add_test(NAME tasks COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/tasks.py $<TARGET_FILE:nex>)
add_test(NAME task_toolchains COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_toolchains.py $<TARGET_FILE:nex>)
if(NEX_Z3_EXECUTABLE)
  set_tests_properties(verification PROPERTIES ENVIRONMENT "NEX_Z3_EXECUTABLE=${NEX_Z3_EXECUTABLE}")
endif()
find_program(NEX_NODE_EXECUTABLE node)
if(NEX_NODE_EXECUTABLE)
  add_test(NAME bytes_values COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/bytes_values.py $<TARGET_FILE:nex_bytes_values_probe> ${NEX_NODE_EXECUTABLE})
  add_test(NAME bytes_runtime COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/bytes_runtime.py $<TARGET_FILE:nex_bytes_runtime_probe> ${NEX_NODE_EXECUTABLE})
  add_test(NAME float_runtime COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/float_runtime.py $<TARGET_FILE:nex_float_runtime_probe> ${NEX_NODE_EXECUTABLE})
  add_test(NAME web COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/web.py $<TARGET_FILE:nex>)
  add_test(NAME web_commands COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/web_commands.py $<TARGET_FILE:nex>)
  set_tests_properties(web PROPERTIES ENVIRONMENT "NEX_NODE=${NEX_NODE_EXECUTABLE}")
  set_tests_properties(web_commands PROPERTIES ENVIRONMENT "NEX_NODE=${NEX_NODE_EXECUTABLE}")
endif()

add_test(NAME enums COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/enums.py $<TARGET_FILE:nex>)

add_test(NAME generics COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/generics.py $<TARGET_FILE:nex>)
add_test(NAME constraints COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/constraints.py $<TARGET_FILE:nex>)
add_test(NAME matching COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/matching.py $<TARGET_FILE:nex>)

add_test(NAME function_values COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/function_values.py $<TARGET_FILE:nex>)
add_test(NAME function_debug COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/function_debug.py $<TARGET_FILE:nex>)
add_test(NAME bytes COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/bytes.py $<TARGET_FILE:nex>)
add_test(NAME bytes_debug COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/bytes_debug.py $<TARGET_FILE:nex>)
add_test(NAME numbers COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/numbers.py $<TARGET_FILE:nex>)
