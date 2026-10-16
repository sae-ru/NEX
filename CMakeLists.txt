cmake_minimum_required(VERSION 3.25)
project(NEX VERSION 0.9.0 LANGUAGES C CXX)
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

add_library(nex_frontend src/language.cpp src/interpreter.cpp src/modules.cpp src/wire_schema.cpp runtime/nex_json.cpp runtime/nex_store.cpp)
target_include_directories(nex_frontend PUBLIC include)
target_include_directories(nex_frontend PRIVATE runtime)
target_include_directories(nex_frontend SYSTEM PUBLIC ${LLVM_INCLUDE_DIRS})
target_link_libraries(nex_frontend PUBLIC LLVM SQLite::SQLite3)
target_compile_definitions(nex_frontend PRIVATE NEX_RESOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_options(nex_frontend PRIVATE -Wall -Wextra -Wpedantic)
add_executable(nex src/main.cpp src/backend.cpp src/incremental.cpp src/project.cpp src/typescript.cpp src/web.cpp src/api.cpp)
target_include_directories(nex PRIVATE runtime)
target_include_directories(nex SYSTEM PRIVATE ${MLIR_INCLUDE_DIRS})
target_link_libraries(nex PRIVATE nex_frontend MLIR SQLite::SQLite3)
target_compile_options(nex PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(nex PRIVATE
  NEX_VERSION="${PROJECT_VERSION}"
  NEX_BUILD_ID="${NEX_BUILD_ID}"
  NEX_RUNTIME_SOURCE="${CMAKE_CURRENT_SOURCE_DIR}/runtime/runtime.cpp"
  NEX_LLVM_TOOLS="${LLVM_TOOLS_BINARY_DIR}"
  NEX_CLANG="${LLVM_TOOLS_BINARY_DIR}/clang++")
target_compile_definitions(nex PRIVATE NEX_SQLITE_INCLUDE="${SQLite3_INCLUDE_DIRS}" NEX_SQLITE_LIBRARY="${SQLite3_LIBRARIES}")
target_compile_definitions(nex PRIVATE NEX_OPENSSL_INCLUDE="${OPENSSL_INCLUDE_DIR}" NEX_OPENSSL_SSL="${OPENSSL_SSL_LIBRARY}" NEX_OPENSSL_CRYPTO="${OPENSSL_CRYPTO_LIBRARY}")
set_target_properties(nex PROPERTIES BUILD_RPATH "${LLVM_LIBRARY_DIRS}" INSTALL_RPATH "${LLVM_LIBRARY_DIRS}")
install(TARGETS nex RUNTIME DESTINATION bin)
install(DIRECTORY docs llm runtime examples lib web debug DESTINATION share/nex
  PATTERN node_modules EXCLUDE PATTERN test-results EXCLUDE PATTERN playwright-report EXCLUDE
  PATTERN .nex EXCLUDE PATTERN generated EXCLUDE PATTERN __pycache__ EXCLUDE)
install(FILES AGENTS.md README.md STATUS.md PLAN.md THIRD_PARTY.md DESTINATION share/nex)
enable_testing()
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
add_test(NAME incremental COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/incremental.py $<TARGET_FILE:nex>)
find_program(NEX_NODE_EXECUTABLE node)
if(NEX_NODE_EXECUTABLE)
  add_test(NAME web COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/web.py $<TARGET_FILE:nex>)
  add_test(NAME web_commands COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/web_commands.py $<TARGET_FILE:nex>)
  set_tests_properties(web PROPERTIES ENVIRONMENT "NEX_NODE=${NEX_NODE_EXECUTABLE}")
  set_tests_properties(web_commands PROPERTIES ENVIRONMENT "NEX_NODE=${NEX_NODE_EXECUTABLE}")
endif()
