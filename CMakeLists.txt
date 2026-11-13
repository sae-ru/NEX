cmake_minimum_required(VERSION 3.25)
# Single source of truth for the toolchain version; remaining version checks
# live in tools/ and compare current documents against this file.
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" NEX_VERSION LIMIT_COUNT 1)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION")
if(NOT NEX_VERSION MATCHES "^[0-9]+\\.[0-9]+\\.[0-9]+$")
  message(FATAL_ERROR "VERSION must contain one semantic version, got '${NEX_VERSION}'")
endif()
project(NEX VERSION ${NEX_VERSION} LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(WIN32 AND CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  # Native Windows Ninja response files contain Windows path separators.
  string(APPEND CMAKE_C_FLAGS " --rsp-quoting=windows")
  string(APPEND CMAKE_CXX_FLAGS " --rsp-quoting=windows")
endif()

set(NEX_DEFAULT_TOOLCHAIN "" CACHE FILEPATH "Explicit default target toolchain for this local compiler installation")
# Source package fixtures must receive explicit provenance for private native
# dependencies, including the early private project-protocol fixture below.
set(NEX_PACKAGE_NOTICES_FILE "" CACHE FILEPATH "Operator-selected native dependency notices for source package tests")
set(NEX_TEST_PACKAGE_NOTICES_ARGS)
if(NEX_PACKAGE_NOTICES_FILE)
  if(NOT EXISTS "${NEX_PACKAGE_NOTICES_FILE}" OR IS_DIRECTORY "${NEX_PACKAGE_NOTICES_FILE}")
    message(FATAL_ERROR "NEX_PACKAGE_NOTICES_FILE must name the actual dependency notice inventory")
  endif()
  list(APPEND NEX_TEST_PACKAGE_NOTICES_ARGS --package-notices "${NEX_PACKAGE_NOTICES_FILE}")
endif()

if(NOT LLVM_DIR AND EXISTS "/opt/homebrew/opt/llvm@22/lib/cmake/llvm")
  set(LLVM_DIR "/opt/homebrew/opt/llvm@22/lib/cmake/llvm")
endif()
find_package(LLVM CONFIG REQUIRED)
if(LLVM_VERSION_MAJOR LESS 22 OR LLVM_VERSION_MAJOR GREATER 23)
  message(FATAL_ERROR "NEX requires LLVM/MLIR 22.1.x or 23.1.x, found ${LLVM_PACKAGE_VERSION}")
endif()
find_package(MLIR REQUIRED CONFIG HINTS "${LLVM_INSTALL_PREFIX}/lib/cmake/mlir")
find_program(NEX_WASM_LD NAMES wasm-ld HINTS "${LLVM_TOOLS_BINARY_DIR}")
if(NOT NEX_WASM_LD)
  set(NEX_WASM_LD "")
endif()
find_package(SQLite3 3.37 REQUIRED)
if(NOT OPENSSL_ROOT_DIR AND EXISTS "/opt/homebrew/opt/openssl@3")
  set(OPENSSL_ROOT_DIR "/opt/homebrew/opt/openssl@3")
endif()
# OpenSSL 4 is accepted for the qualified Fedora 45 cohort; older 3.x remains supported.
find_package(OpenSSL 3...<5 REQUIRED)
# Source-only native acceptance executables must also run after SDK paths
# disappear. Prefer the genuine Windows archives for their private test hosts.
set(NEX_PRIVATE_CRYPTO_LIBRARY "${OPENSSL_CRYPTO_LIBRARY}")
set(NEX_PRIVATE_SSL_LIBRARY "${OPENSSL_SSL_LIBRARY}")
set(NEX_PRIVATE_SQLITE_LIBRARY "${SQLite3_LIBRARY}")
if(WIN32)
  foreach(NEX_PRIVATE_DEPENDENCY IN ITEMS CRYPTO SSL SQLITE)
    get_filename_component(NEX_PRIVATE_LIBDIR "${NEX_PRIVATE_${NEX_PRIVATE_DEPENDENCY}_LIBRARY}" DIRECTORY)
    string(TOLOWER "${NEX_PRIVATE_DEPENDENCY}" NEX_PRIVATE_LIBNAME)
    if(NEX_PRIVATE_DEPENDENCY STREQUAL "SQLITE")
      set(NEX_PRIVATE_LIBNAME sqlite3)
    endif()
    if(EXISTS "${NEX_PRIVATE_LIBDIR}/lib${NEX_PRIVATE_LIBNAME}.a")
      set(NEX_PRIVATE_${NEX_PRIVATE_DEPENDENCY}_LIBRARY "${NEX_PRIVATE_LIBDIR}/lib${NEX_PRIVATE_LIBNAME}.a")
    endif()
  endforeach()
endif()

set(NEX_Z3_ROOT "" CACHE PATH "Z3 development installation prefix")
if(APPLE AND NOT NEX_Z3_ROOT AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/build/deps/z3-5.3.1-arm64-osx-13.3")
  set(NEX_Z3_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/build/deps/z3-5.3.1-arm64-osx-13.3")
endif()
find_path(NEX_Z3_INCLUDE z3++.h HINTS "${NEX_Z3_ROOT}/include" PATH_SUFFIXES z3 REQUIRED)
find_library(NEX_Z3_LIBRARY NAMES z3 libz3 HINTS "${NEX_Z3_ROOT}/lib" "${NEX_Z3_ROOT}/bin" REQUIRED)
find_program(NEX_Z3_EXECUTABLE z3 HINTS "${NEX_Z3_ROOT}/bin")
get_filename_component(NEX_Z3_LIBRARY_DIR "${NEX_Z3_LIBRARY}" DIRECTORY)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
message(STATUS "NEX uses LLVM ${LLVM_PACKAGE_VERSION} and MLIR at ${MLIR_DIR}")

file(GLOB_RECURSE NEX_COMPILER_FILES CONFIGURE_DEPENDS "src/*.cpp" "src/*.h" "include/*.h" "runtime/*.cpp" "runtime/*.c" "runtime/*.h" "runtime/*.hpp" "runtime/*.manifest")
list(APPEND NEX_COMPILER_FILES "${CMAKE_CURRENT_SOURCE_DIR}/tools/windows/nex.manifest" "${CMAKE_CURRENT_SOURCE_DIR}/tools/windows/nex.rc.in")
list(APPEND NEX_COMPILER_FILES "${CMAKE_CURRENT_SOURCE_DIR}/lib/text.nex"
  "${CMAKE_CURRENT_SOURCE_DIR}/lib/list.nex" "${CMAKE_CURRENT_SOURCE_DIR}/lib/math.nex"
  "${CMAKE_CURRENT_SOURCE_DIR}/lib/map.nex" "${CMAKE_CURRENT_SOURCE_DIR}/lib/set.nex"
  "${CMAKE_CURRENT_SOURCE_DIR}/lib/queue.nex" "${CMAKE_CURRENT_SOURCE_DIR}/lib/stack.nex"
  "${CMAKE_CURRENT_SOURCE_DIR}/lib/deque.nex"
  "${CMAKE_CURRENT_SOURCE_DIR}/lib/priority_queue.nex")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${NEX_COMPILER_FILES})
set(NEX_BUILD_INPUTS "${PROJECT_VERSION};${LLVM_PACKAGE_VERSION};${CMAKE_CXX_COMPILER_ID};${CMAKE_CXX_COMPILER_VERSION};${CMAKE_BUILD_TYPE}")
if(NEX_DEFAULT_TOOLCHAIN)
  file(SHA256 "${NEX_DEFAULT_TOOLCHAIN}" NEX_DEFAULT_TOOLCHAIN_HASH)
  string(APPEND NEX_BUILD_INPUTS ";${NEX_DEFAULT_TOOLCHAIN};${NEX_DEFAULT_TOOLCHAIN_HASH}")
endif()
foreach(NEX_INPUT IN LISTS NEX_COMPILER_FILES)
  file(SHA256 "${NEX_INPUT}" NEX_INPUT_HASH)
  string(APPEND NEX_BUILD_INPUTS ";${NEX_INPUT_HASH}")
endforeach()
string(SHA256 NEX_BUILD_ID "${NEX_BUILD_INPUTS}")

add_library(nex_frontend src/frontend_diagnostics.cpp src/language.cpp src/generics.cpp src/matching.cpp src/interpreter.cpp src/watch_values.cpp src/debug_values.cpp src/operations.cpp src/modules.cpp src/wire_schema.cpp src/foreign_schema.cpp runtime/nex_foreign.cpp runtime/nex_ffi_loader.cpp runtime/nex_ffi.cpp runtime/nex_ffi_types.cpp runtime/nex_ffi_resources.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp runtime/nex_resource_executor.cpp runtime/nex_json.cpp runtime/nex_store.cpp runtime/nex_files.cpp)
# language.cpp's JSON formatter does not need RTTI. Some retained LLVM
# distributions omit the format_adapter typeinfo from static archives; keeping
# this translation unit RTTI-free preserves those builds without weakening the
# runtime's dynamic_cast checks.
if(NOT MSVC)
  set_source_files_properties(src/language.cpp PROPERTIES COMPILE_OPTIONS "-fno-rtti")
endif()
target_sources(nex_frontend PRIVATE src/constructor_types.cpp src/traits.cpp src/source_errors.cpp)
target_sources(nex_frontend PRIVATE src/migration.cpp)
target_sources(nex_frontend PRIVATE src/diagnostic_catalogue.cpp)
target_sources(nex_frontend PRIVATE src/standard_library.cpp)
target_sources(nex_frontend PRIVATE src/formatting.cpp)
target_sources(nex_frontend PRIVATE src/cli_catalogue.cpp src/cli_help.cpp)
target_sources(nex_frontend PRIVATE src/list_build.cpp src/text_build.cpp src/bytes_build.cpp)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  lib/text.nex lib/list.nex lib/math.nex lib/map.nex lib/set.nex
  lib/queue.nex lib/stack.nex lib/deque.nex lib/priority_queue.nex)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/text.nex" NEX_STDLIB_TEXT_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/list.nex" NEX_STDLIB_LIST_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/math.nex" NEX_STDLIB_MATH_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/map.nex" NEX_STDLIB_MAP_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/set.nex" NEX_STDLIB_SET_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/queue.nex" NEX_STDLIB_QUEUE_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/stack.nex" NEX_STDLIB_STACK_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/deque.nex" NEX_STDLIB_DEQUE_SHA256)
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/lib/priority_queue.nex" NEX_STDLIB_PRIORITY_QUEUE_SHA256)
set_source_files_properties(src/standard_library.cpp PROPERTIES COMPILE_DEFINITIONS
  "NEX_STDLIB_TEXT_SHA256=\"${NEX_STDLIB_TEXT_SHA256}\";NEX_STDLIB_LIST_SHA256=\"${NEX_STDLIB_LIST_SHA256}\";NEX_STDLIB_MATH_SHA256=\"${NEX_STDLIB_MATH_SHA256}\";NEX_STDLIB_MAP_SHA256=\"${NEX_STDLIB_MAP_SHA256}\";NEX_STDLIB_SET_SHA256=\"${NEX_STDLIB_SET_SHA256}\";NEX_STDLIB_QUEUE_SHA256=\"${NEX_STDLIB_QUEUE_SHA256}\";NEX_STDLIB_STACK_SHA256=\"${NEX_STDLIB_STACK_SHA256}\";NEX_STDLIB_DEQUE_SHA256=\"${NEX_STDLIB_DEQUE_SHA256}\";NEX_STDLIB_PRIORITY_QUEUE_SHA256=\"${NEX_STDLIB_PRIORITY_QUEUE_SHA256}\"")
target_sources(nex_frontend PRIVATE src/editor.cpp src/task_frontend.cpp src/task_lifetime.cpp src/task_ir.cpp src/task_machine.cpp src/task_ast.cpp src/task_reference.cpp)
target_sources(nex_frontend PRIVATE runtime/runtime.cpp)
target_include_directories(nex_frontend PUBLIC include runtime)
target_include_directories(nex_frontend PRIVATE runtime)
target_include_directories(nex_frontend SYSTEM PUBLIC ${LLVM_INCLUDE_DIRS})
target_link_libraries(nex_frontend PUBLIC LLVM SQLite::SQLite3 OpenSSL::Crypto ${CMAKE_DL_LIBS})
if(WIN32)
  target_link_libraries(nex_frontend PUBLIC ntdll bcrypt advapi32)
endif()
target_compile_definitions(nex_frontend PRIVATE NEX_RESOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_options(nex_frontend PRIVATE -Wall -Wextra -Wpedantic)
add_library(nex_native_backend STATIC src/backend.cpp src/private_task_modules.cpp src/native_toolchain.cpp
  src/native_image_identity.cpp src/incremental.cpp src/task_debug_manifest.cpp src/native_runtime_paths.cpp)
target_link_libraries(nex_native_backend PUBLIC nex_frontend MLIR)
if(WIN32)
  # The CLANG64 MLIR DLL exports the C facade, not the C++ backend API.
  # Keep the exact checked conversion pipeline and link its native components.
  target_link_libraries(nex_native_backend PUBLIC
    MLIRIR MLIRParser MLIRPass MLIRArithDialect MLIRControlFlowDialect
    MLIRFuncDialect MLIRMemRefDialect MLIRLLVMDialect MLIRLLVMIRTransforms
    MLIRArithToLLVM MLIRFuncToLLVM MLIRMemRefToLLVM MLIRControlFlowToLLVM
    MLIRReconcileUnrealizedCasts MLIRBuiltinToLLVMIRTranslation MLIRLLVMToLLVMIRTranslation)
endif()
add_executable(nex src/main.cpp src/native_diagnostics.cpp src/debugging.cpp src/profiling.cpp src/verification.cpp src/tasks.cpp src/task_process.cpp src/project.cpp src/graph_snapshot.cpp src/change_store.cpp src/operation_store.cpp src/graph_store.cpp src/typescript.cpp src/web.cpp src/api.cpp src/packaging.cpp src/foreign_catalogue.cpp)
if(WIN32)
  if(NOT CMAKE_RC_COMPILER)
    set(CMAKE_RC_COMPILER "${LLVM_TOOLS_BINARY_DIR}/llvm-windres.exe" CACHE FILEPATH "Native Windows resource compiler")
  endif()
  enable_language(RC)
  configure_file(tools/windows/nex.rc.in "${CMAKE_CURRENT_BINARY_DIR}/nex-host.rc" @ONLY)
  target_sources(nex PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/nex-host.rc")
endif()
target_include_directories(nex PRIVATE runtime)
target_sources(nex PRIVATE src/core_dump.cpp src/discovery.cpp)
target_sources(nex PRIVATE src/task_profile_report.cpp)
target_sources(nex PRIVATE src/task_package.cpp src/server_workload.cpp src/task_workload.cpp)
target_sources(nex PRIVATE src/wasm.cpp src/project_build.cpp src/native_images.cpp src/debug_session.cpp src/project_capture.cpp)
target_sources(nex PRIVATE src/metal.cpp src/cuda.cpp src/opencl.cpp)
target_sources(nex PRIVATE src/graph_migration.cpp)
target_include_directories(nex SYSTEM PRIVATE ${MLIR_INCLUDE_DIRS})
target_include_directories(nex SYSTEM PRIVATE ${NEX_Z3_INCLUDE})
target_link_libraries(nex PRIVATE nex_native_backend nex_frontend MLIR SQLite::SQLite3 ${NEX_Z3_LIBRARY})
target_compile_options(nex PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(nex PRIVATE
  NEX_VERSION="${PROJECT_VERSION}"
  NEX_BUILD_ID="${NEX_BUILD_ID}"
  NEX_DEFAULT_TOOLCHAIN="${NEX_DEFAULT_TOOLCHAIN}"
  NEX_RUNTIME_SOURCE="${CMAKE_CURRENT_SOURCE_DIR}/runtime/runtime.cpp"
  NEX_LLVM_TOOLS="${LLVM_TOOLS_BINARY_DIR}"
  NEX_WASM_LD="${NEX_WASM_LD}"
  NEX_CLANG="${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}")
target_compile_definitions(nex PRIVATE NEX_SQLITE_INCLUDE="${SQLite3_INCLUDE_DIRS}" NEX_SQLITE_LIBRARY="${SQLite3_LIBRARIES}")
target_compile_definitions(nex PRIVATE NEX_OPENSSL_INCLUDE="${OPENSSL_INCLUDE_DIR}" NEX_OPENSSL_SSL="${OPENSSL_SSL_LIBRARY}" NEX_OPENSSL_CRYPTO="${OPENSSL_CRYPTO_LIBRARY}")
include(cmake/Install.cmake)
include(cmake/Tests.cmake)
include(cmake/TestTiers.cmake)
