cmake_minimum_required(VERSION 3.25)
project(NEX VERSION 0.164.0 LANGUAGES C CXX)
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
find_package(LLVM 22.1.0 REQUIRED CONFIG)
find_package(MLIR REQUIRED CONFIG HINTS "${LLVM_INSTALL_PREFIX}/lib/cmake/mlir")
find_program(NEX_WASM_LD NAMES wasm-ld HINTS "${LLVM_TOOLS_BINARY_DIR}")
if(NOT NEX_WASM_LD)
  set(NEX_WASM_LD "")
endif()
find_package(SQLite3 3.37 REQUIRED)
if(NOT OPENSSL_ROOT_DIR AND EXISTS "/opt/homebrew/opt/openssl@3")
  set(OPENSSL_ROOT_DIR "/opt/homebrew/opt/openssl@3")
endif()
# OpenSSL4 TLS environment handling and package closure are not qualified yet.
find_package(OpenSSL 3...<4 REQUIRED)
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

file(GLOB_RECURSE NEX_COMPILER_FILES CONFIGURE_DEPENDS "src/*.cpp" "include/*.h" "runtime/*.cpp" "runtime/*.c" "runtime/*.h" "runtime/*.hpp" "runtime/*.manifest")
list(APPEND NEX_COMPILER_FILES "${CMAKE_CURRENT_SOURCE_DIR}/tools/windows/nex.manifest" "${CMAKE_CURRENT_SOURCE_DIR}/tools/windows/nex.rc.in")
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
target_sources(nex_frontend PRIVATE src/constructor_types.cpp src/traits.cpp src/source_errors.cpp)
target_sources(nex_frontend PRIVATE src/migration.cpp)
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
# The production executable and the private native-stage probe use the same
# backend objects, compiler identity and selected toolchain defaults.
get_target_property(NEX_NATIVE_DEFINITIONS nex COMPILE_DEFINITIONS)
if(WIN32)
  add_executable(nex_windows_host_runtime_probe tests/windows_host_runtime.cpp "${CMAKE_CURRENT_BINARY_DIR}/nex-host.rc")
  target_include_directories(nex_windows_host_runtime_probe PRIVATE runtime)
  target_link_libraries(nex_windows_host_runtime_probe PRIVATE nex_frontend)
  add_test(NAME windows_host_runtime COMMAND nex_windows_host_runtime_probe "${CMAKE_CURRENT_BINARY_DIR}/host-runtime-artifacts")
  set_tests_properties(windows_host_runtime PROPERTIES TIMEOUT 120)
endif()
target_compile_definitions(nex_native_backend PRIVATE ${NEX_NATIVE_DEFINITIONS})
target_include_directories(nex_native_backend PRIVATE runtime)
target_include_directories(nex_native_backend SYSTEM PRIVATE ${MLIR_INCLUDE_DIRS})
target_compile_options(nex_native_backend PRIVATE -Wall -Wextra -Wpedantic)
get_target_property(NEX_PRIVATE_PROJECT_SOURCES nex SOURCES)
list(REMOVE_ITEM NEX_PRIVATE_PROJECT_SOURCES src/main.cpp)
add_executable(nex_task_stream_project_probe tests/task_stream_project_probe.cpp ${NEX_PRIVATE_PROJECT_SOURCES})
target_link_libraries(nex_task_stream_project_probe PRIVATE nex_native_backend nex_frontend MLIR SQLite::SQLite3 ${NEX_Z3_LIBRARY})
target_include_directories(nex_task_stream_project_probe PRIVATE runtime)
target_include_directories(nex_task_stream_project_probe SYSTEM PRIVATE ${MLIR_INCLUDE_DIRS} ${NEX_Z3_INCLUDE})
target_compile_definitions(nex_task_stream_project_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
target_compile_options(nex_task_stream_project_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_stream_project COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_project.py $<TARGET_FILE:nex_task_stream_project_probe> $<TARGET_FILE:nex> $<TARGET_FILE:nex_source_resource_probe> --complete-tooling ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(task_stream_project PROPERTIES TIMEOUT 3600)
add_executable(nex_native_staging_probe tests/native_staging.cpp)
target_link_libraries(nex_native_staging_probe PRIVATE nex_native_backend)
if(UNIX)
  # Some LLVM installations package ELF LLD separately from Clang and Wasm LLD.
  # Keep the test registered when it is absent: a full suite must provision it.
  find_program(NEX_ELF_TEST_LD NAMES ld.lld HINTS "${LLVM_TOOLS_BINARY_DIR}")
  add_executable(nex_native_runtime_paths_probe tests/native_runtime_paths.cpp)
  target_link_libraries(nex_native_runtime_paths_probe PRIVATE nex_native_backend)
  add_test(NAME native_runtime_paths COMMAND ${Python3_EXECUTABLE} -B
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_runtime_paths.py
    $<TARGET_FILE:nex_native_runtime_paths_probe> ${LLVM_TOOLS_BINARY_DIR}/clang
    ${NEX_ELF_TEST_LD} ${LLVM_TOOLS_BINARY_DIR}/llvm-ar)
  set_tests_properties(native_runtime_paths PROPERTIES TIMEOUT 120)
  if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    add_test(NAME native_runtime_loader COMMAND ${Python3_EXECUTABLE} -B
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_runtime_paths.py
      $<TARGET_FILE:nex_native_runtime_paths_probe> ${LLVM_TOOLS_BINARY_DIR}/clang
      ${NEX_ELF_TEST_LD} ${LLVM_TOOLS_BINARY_DIR}/llvm-ar --loader)
    set_tests_properties(native_runtime_loader PROPERTIES TIMEOUT 120)
  endif()
endif()
add_executable(nex_task_native_emit_probe tests/task_native_emit.cpp)
target_link_libraries(nex_task_native_emit_probe PRIVATE nex_native_backend)
add_executable(nex_task_typescript_emit_probe tests/task_typescript_emit.cpp src/typescript.cpp)
target_link_libraries(nex_task_typescript_emit_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_options(nex_task_typescript_emit_probe PRIVATE -Wall -Wextra -Wpedantic)
add_executable(nex_source_resource_probe tests/source_resource_probe.cpp src/typescript.cpp)
target_link_libraries(nex_source_resource_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_options(nex_source_resource_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_file_stream_mixed COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_mixed.py $<TARGET_FILE:nex_source_resource_probe>)
set_tests_properties(task_file_stream_mixed PROPERTIES TIMEOUT 1800)
add_test(NAME source_external_resources COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_resources.py $<TARGET_FILE:nex_source_resource_probe>
  ${CMAKE_CURRENT_SOURCE_DIR} --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --nex $<TARGET_FILE:nex>)
set_tests_properties(source_external_resources PROPERTIES TIMEOUT 600)
add_test(NAME source_task_foreign_prototype COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_foreign_source.py $<TARGET_FILE:nex_source_resource_probe>
  --context-probe $<TARGET_FILE:nex_task_foreign_context_probe>)
set_tests_properties(source_task_foreign_prototype PROPERTIES TIMEOUT 600)
add_test(NAME source_task_resource_prototype COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_resource_source.py $<TARGET_FILE:nex_source_resource_probe>
  --context-probe $<TARGET_FILE:nex_task_owned_foreign_context_probe>)
set_tests_properties(source_task_resource_prototype PROPERTIES TIMEOUT 900)
add_executable(nex_resource_transfers_probe tests/resource_transfers.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp runtime/nex_resource_executor.cpp)
target_include_directories(nex_resource_transfers_probe PRIVATE runtime)
target_link_libraries(nex_resource_transfers_probe PRIVATE Threads::Threads)
target_compile_options(nex_resource_transfers_probe PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(nex_resource_transfers_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
add_test(NAME atomic_resource_transfers COMMAND nex_resource_transfers_probe)
add_executable(nex_task_owned_foreign_context_probe tests/task_owned_foreign_context.cpp)
target_link_libraries(nex_task_owned_foreign_context_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_owned_foreign_context_probe PRIVATE -Wall -Wextra -Wpedantic)
add_executable(nex_task_foreign_context_probe tests/task_foreign_context.cpp)
target_link_libraries(nex_task_foreign_context_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_foreign_context_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME source_task_foreign_genuine021_origins COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_foreign_origins.py $<TARGET_FILE:nex_source_resource_probe>)
set_tests_properties(source_task_foreign_genuine021_origins PROPERTIES TIMEOUT 120)
add_test(NAME public_task_foreign_source COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_foreign_source.py $<TARGET_FILE:nex_source_resource_probe>
  --context-probe $<TARGET_FILE:nex_task_foreign_context_probe> --compiler $<TARGET_FILE:nex>)
add_test(NAME public_task_resource_source COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_resource_source.py $<TARGET_FILE:nex_source_resource_probe>
  --context-probe $<TARGET_FILE:nex_task_owned_foreign_context_probe> --compiler $<TARGET_FILE:nex>)
set_tests_properties(public_task_foreign_source public_task_resource_source PROPERTIES TIMEOUT 1800)

add_test(NAME source_task_foreign_genuine021_history COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_foreign_history.py $<TARGET_FILE:nex_task_migration_probe> $<TARGET_FILE:nex_source_resource_probe> $<TARGET_FILE:nex>)
set_tests_properties(source_task_foreign_genuine021_history PROPERTIES TIMEOUT 900)
add_test(NAME public_task_foreign_language_migration COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_foreign_migration.py $<TARGET_FILE:nex_task_migration_probe> $<TARGET_FILE:nex>)
set_tests_properties(public_task_foreign_language_migration PROPERTIES TIMEOUT 1800)

add_test(NAME resource_language_migration COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/resource_migration.py $<TARGET_FILE:nex_task_migration_probe> $<TARGET_FILE:nex>)
set_tests_properties(resource_language_migration PROPERTIES TIMEOUT 600)
add_test(NAME source_resource_debugger COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_resource_debug.py $<TARGET_FILE:nex> ${CMAKE_CURRENT_SOURCE_DIR})
set_tests_properties(source_resource_debugger PROPERTIES TIMEOUT 300)
add_executable(nex_resource_dependencies_probe tests/resource_dependencies.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp runtime/nex_resource_executor.cpp)
target_include_directories(nex_resource_dependencies_probe PRIVATE runtime)
target_link_libraries(nex_resource_dependencies_probe PRIVATE Threads::Threads)
target_compile_options(nex_resource_dependencies_probe PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(nex_resource_dependencies_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
add_test(NAME resource_dependency_lifetimes COMMAND nex_resource_dependencies_probe)
set_tests_properties(resource_dependency_lifetimes PROPERTIES TIMEOUT 60)
add_test(NAME dependent_resource_source COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/resource_dependency_source.py --compiler $<TARGET_FILE:nex>)
set_tests_properties(dependent_resource_source PROPERTIES TIMEOUT 1800)

add_executable(nex_resource_executor_probe tests/resource_executor.cpp runtime/nex_resource_executor.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp)
target_include_directories(nex_resource_executor_probe PRIVATE runtime)
target_compile_options(nex_resource_executor_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_resource_executor_probe PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
add_library(nex_resource_executor_fixture MODULE tests/resource_executor_module.cpp)
target_include_directories(nex_resource_executor_fixture PRIVATE runtime)
add_test(NAME owned_resource_executor COMMAND nex_resource_executor_probe $<TARGET_FILE:nex_resource_executor_fixture>)
set_tests_properties(owned_resource_executor PROPERTIES TIMEOUT 90)
add_executable(nex_resource_regions_probe tests/resource_regions.cpp runtime/runtime.cpp runtime/nex_files.cpp
  runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp runtime/nex_task_external.cpp)
target_include_directories(nex_resource_regions_probe PRIVATE runtime)
target_compile_definitions(nex_resource_regions_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(nex_resource_regions_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_resource_regions_probe PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
add_test(NAME logical_resource_regions COMMAND nex_resource_regions_probe)
set_tests_properties(logical_resource_regions PROPERTIES TIMEOUT 90)
add_executable(nex_reference_resource_regions_probe tests/resource_regions_reference.cpp)
target_link_libraries(nex_reference_resource_regions_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_reference_resource_regions_probe PRIVATE -Wall -Wextra -Wpedantic)
add_executable(nex_reference_retirement_race_probe tests/reference_retirement_race.cpp src/task_reference.cpp)
target_link_libraries(nex_reference_retirement_race_probe PRIVATE nex_frontend Threads::Threads)
target_compile_definitions(nex_reference_retirement_race_probe PRIVATE NEX_REFERENCE_RETIREMENT_TEST_HOOK)
add_test(NAME reference_retirement_progress COMMAND nex_reference_retirement_race_probe)
set_tests_properties(reference_retirement_progress PROPERTIES TIMEOUT 30)
add_test(NAME reference_resource_regions COMMAND nex_reference_resource_regions_probe)
set_tests_properties(reference_resource_regions PROPERTIES TIMEOUT 90)
add_executable(nex_reference_request_resources_probe tests/resource_requests_reference.cpp)
target_link_libraries(nex_reference_request_resources_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_reference_request_resources_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME reference_request_resources COMMAND nex_reference_request_resources_probe)
set_tests_properties(reference_request_resources PROPERTIES TIMEOUT 120)
foreach(NEX_REQUEST_GATE request_resource_regions native_request_resources)
  add_executable(nex_${NEX_REQUEST_GATE}_probe tests/${NEX_REQUEST_GATE}.cpp
    runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_external_resource.cpp
    runtime/nex_resource_executor.cpp runtime/nex_task_external.cpp)
  target_include_directories(nex_${NEX_REQUEST_GATE}_probe PRIVATE runtime)
  target_compile_definitions(nex_${NEX_REQUEST_GATE}_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
  target_compile_options(nex_${NEX_REQUEST_GATE}_probe PRIVATE -Wall -Wextra -Wpedantic)
  target_link_libraries(nex_${NEX_REQUEST_GATE}_probe PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
  add_test(NAME ${NEX_REQUEST_GATE} COMMAND nex_${NEX_REQUEST_GATE}_probe)
  set_tests_properties(${NEX_REQUEST_GATE} PROPERTIES TIMEOUT 120)
endforeach()
add_executable(nex_task_value_retirement_probe tests/task_value_retirement.cpp runtime/runtime.cpp
  runtime/nex_files.cpp runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp runtime/nex_task_external.cpp)
target_include_directories(nex_task_value_retirement_probe PRIVATE runtime)
target_compile_definitions(nex_task_value_retirement_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(nex_task_value_retirement_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_task_value_retirement_probe PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
add_test(NAME task_value_retirement COMMAND nex_task_value_retirement_probe)
set_tests_properties(task_value_retirement PROPERTIES TIMEOUT 90)

add_test(NAME task_typescript_steps COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_typescript.py $<TARGET_FILE:nex_task_typescript_emit_probe> $<TARGET_FILE:nex_task_reference_probe>)
set_tests_properties(task_typescript_steps PROPERTIES TIMEOUT 600)
add_test(NAME task_native_steps COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_native.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_task_native_emit_probe> $<TARGET_FILE:nex_task_reference_probe>)
set_tests_properties(task_native_steps PROPERTIES TIMEOUT 1200)
add_executable(nex_native_plan_probe tests/native_plan.cpp)
target_link_libraries(nex_native_plan_probe PRIVATE nex_native_backend)
add_executable(nex_task_static_provider_boundary_probe tests/task_static_provider_boundary.cpp)
target_link_libraries(nex_task_static_provider_boundary_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_task_static_provider_boundary_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME task_static_provider_boundary_native COMMAND nex_task_static_provider_boundary_probe)
set_tests_properties(task_static_provider_boundary_native PROPERTIES TIMEOUT 120)

add_executable(nex_task_provider_profile_boundary_probe tests/task_provider_profile_boundary.cpp)
target_link_libraries(nex_task_provider_profile_boundary_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_task_provider_profile_boundary_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME task_provider_profile_boundary_native COMMAND nex_task_provider_profile_boundary_probe)
set_tests_properties(task_provider_profile_boundary_native PROPERTIES TIMEOUT 120)

add_executable(nex_task_provider_debug_boundary_probe tests/task_provider_debug_boundary.cpp)
target_link_libraries(nex_task_provider_debug_boundary_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_task_provider_debug_boundary_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME task_provider_debug_boundary_native COMMAND nex_task_provider_debug_boundary_probe)
set_tests_properties(task_provider_debug_boundary_native PROPERTIES TIMEOUT 120)

add_executable(nex_task_shared_provider_boundary_probe tests/task_shared_provider_boundary.cpp)
target_link_libraries(nex_task_shared_provider_boundary_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_task_shared_provider_boundary_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME task_shared_provider_boundary_native COMMAND nex_task_shared_provider_boundary_probe)
set_tests_properties(task_shared_provider_boundary_native PROPERTIES TIMEOUT 120)
set_target_properties(nex PROPERTIES BUILD_RPATH "${LLVM_LIBRARY_DIRS};${NEX_Z3_LIBRARY_DIR}" INSTALL_RPATH "${LLVM_LIBRARY_DIRS};${NEX_Z3_LIBRARY_DIR}")
install(TARGETS nex RUNTIME DESTINATION bin)
install(DIRECTORY docs llm runtime examples lib web debug mobile DESTINATION share/nex
  PATTERN node_modules EXCLUDE PATTERN test-results EXCLUDE PATTERN playwright-report EXCLUDE
  PATTERN .nex EXCLUDE PATTERN generated EXCLUDE PATTERN __pycache__ EXCLUDE
  PATTERN .build EXCLUDE PATTERN windows-tic-tac-toe/dist EXCLUDE
  PATTERN windows-tic-tac-toe/src/gui.nex EXCLUDE
  PATTERN tic-tac-toe/dist EXCLUDE PATTERN tic-tac-toe/src/gui.nex EXCLUDE)
install(FILES AGENTS.md README.md README.ru.md LICENSE llms.txt STATUS.md PLAN.md THIRD_PARTY.md DESTINATION share/nex)
install(FILES tests/sqlite_fixture.py tests/host_test.h tests/ffi_marker.h DESTINATION share/nex/tests)
install(DIRECTORY tools/linux DESTINATION share/nex/tools PATTERN __pycache__ EXCLUDE)
install(DIRECTORY tools/accelerators DESTINATION share/nex/tools PATTERN __pycache__ EXCLUDE)
install(DIRECTORY tools/tcp_provider DESTINATION share/nex/tools PATTERN __pycache__ EXCLUDE)
install(DIRECTORY tools/dns_provider DESTINATION share/nex/tools PATTERN __pycache__ EXCLUDE)
install(DIRECTORY tools/http_provider DESTINATION share/nex/tools PATTERN __pycache__ EXCLUDE)
install(DIRECTORY tools/http_stream_provider DESTINATION share/nex/tools PATTERN __pycache__ EXCLUDE)
install(DIRECTORY tools/macos DESTINATION share/nex/tools PATTERN __pycache__ EXCLUDE)
install(FILES tools/sdk_acceptance.py tools/sdk_host.py tools/sdk_source_contracts.py tools/sdk_typed_source.py tools/sdk_task_limits.py tools/sdk_source_exceptions.py tools/sdk_source_handlers.py tools/server_workload.py tools/provider_sdk.py DESTINATION share/nex/tools)
install(FILES tools/compiler_cohort.py DESTINATION share/nex/tools)
install(FILES tools/ctest_report.py DESTINATION share/nex/tools)
install(FILES tests/task_http_server.py DESTINATION share/nex/tests)
install(DIRECTORY experiments/models/ DESTINATION share/nex/tools/models
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/owned-opencl/ DESTINATION share/nex/tools/owned-opencl
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/owned-metal/ DESTINATION share/nex/tools/owned-metal
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/metal/ DESTINATION share/nex/tools/metal
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/owned-cuda/ DESTINATION share/nex/tools/owned-cuda
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/cix-p1/include/ DESTINATION share/nex/tools/owned-opencl/include)
install(FILES tools/sdk_task_file_migration.py DESTINATION share/nex/tools)
install(FILES tools/sdk_source_resources.py DESTINATION share/nex/tools)
install(FILES tests/resource_dependency_source.py tests/source_resource_cli.py tests/dependent_resource_module.c tests/legacy_resource_prefix_module.c tests/legacy_parent_prefix_module.c DESTINATION share/nex/tests)
install(FILES tests/fixtures/ffi-resource-prefix-0.130/nex_ffi.h tests/fixtures/ffi-resource-prefix-0.130/README.md DESTINATION share/nex/tests/fixtures/ffi-resource-prefix-0.130)
install(FILES tests/fixtures/ffi-parent-prefix-0.163/nex_ffi.h tests/fixtures/ffi-parent-prefix-0.163/README.md DESTINATION share/nex/tests/fixtures/ffi-parent-prefix-0.163)
install(FILES tools/sdk_resource_executor.py DESTINATION share/nex/tools)
install(FILES tools/sdk_resource_regions.py DESTINATION share/nex/tools)
install(FILES tools/sdk_request_resources.py DESTINATION share/nex/tools)
install(FILES tests/request_resource_regions.cpp DESTINATION share/nex/tools RENAME request_resource_regions_acceptance.cpp)
install(FILES tests/native_request_resources.cpp DESTINATION share/nex/tools RENAME native_request_resources_acceptance.cpp)
install(FILES tests/resource_regions.cpp DESTINATION share/nex/tools RENAME resource_regions_acceptance.cpp)
install(FILES tools/sdk_task_value_retirement.py DESTINATION share/nex/tools)
install(FILES tests/task_value_retirement.cpp DESTINATION share/nex/tools RENAME task_value_retirement_acceptance.cpp)
install(FILES tests/resource_executor.cpp DESTINATION share/nex/tools RENAME resource_executor_acceptance.cpp)
install(FILES tests/resource_executor_module.cpp DESTINATION share/nex/tools)
install(FILES tests/source_resource_debug.py DESTINATION share/nex/tools RENAME resource_debug_acceptance.py)
file(GLOB NEX_RESOURCE_MIGRATION_FIXTURES CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/language-0.20-sdk122-resource-*.json"
  "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/language-0.20-sdk122-resource-*.sql")
install(FILES ${NEX_RESOURCE_MIGRATION_FIXTURES} DESTINATION share/nex/examples/resource-migration)
file(GLOB NEX_TASK_FOREIGN_MIGRATION_FIXTURES CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/language-0.21-sdk128-task-foreign-*.json"
  "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/language-0.21-sdk128-task-foreign-*.sql")
install(FILES ${NEX_TASK_FOREIGN_MIGRATION_FIXTURES} DESTINATION share/nex/examples/task-foreign-migration)
install(FILES experiments/quality/scale_100x100.py
  experiments/quality/acceptance_support.py experiments/quality/server_web_edit.py
  experiments/quality/server_web_edit.spec.mjs experiments/quality/type_edit_workflow.py
  experiments/quality/task_cleanup_workflow.py experiments/quality/repair_workflow.py
  experiments/quality/quality_dap.py experiments/quality/run_acceptance.py DESTINATION share/nex/tools)
install(FILES tests/task_provider_debug_lifetime.py DESTINATION share/nex/tools RENAME quality_task_fence.py)
install(FILES tests/task_provider_debug_lifetime.cpp DESTINATION share/nex/tools RENAME quality_task_fence.cpp)
install(FILES experiments/quality/llm_cost.py DESTINATION share/nex/tools)
install(FILES experiments/quality/README.md experiments/quality/llm_cost.md
  DESTINATION share/nex/experiments/quality COMPONENT Documentation)
install(FILES tests/fixtures/language-0.19-sdk115-history.json tests/fixtures/language-0.19-sdk115-history.sql tests/fixtures/language-0.19-sdk115-tasks.json tests/fixtures/language-0.19-sdk115-tasks.sql tests/fixtures/language-0.19-sdk115-fs-helper.json tests/fixtures/language-0.19-sdk115-fs-helper.sql DESTINATION share/nex/examples/task-migration)
install(FILES tools/mobile_project.py DESTINATION share/nex/tools)
install(FILES tools/core_capsule.py DESTINATION share/nex/tools)
install(FILES tools/sdk_bundle.py tools/windows_pe.py tools/windows_files.py DESTINATION share/nex/tools)
install(FILES tools/sdk_archive.py DESTINATION share/nex/tools)
install(FILES tools/app_bundle.py DESTINATION share/nex/tools)
install(FILES tools/foreign_bundle.py DESTINATION share/nex/tools)
install(FILES tools/application_acceptance.py DESTINATION share/nex/tools)
install(DIRECTORY editor DESTINATION share/nex PATTERN node_modules EXCLUDE PATTERN "*.vsix" EXCLUDE)
enable_testing()
if(WIN32)
  add_test(NAME windows_workload_ownership COMMAND ${Python3_EXECUTABLE} -B
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/windows_workload_ownership.py)
  set_tests_properties(windows_workload_ownership PROPERTIES TIMEOUT 30)
  add_test(NAME windows_file_fixture COMMAND ${Python3_EXECUTABLE} -B
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/windows_file_fixture.py
    --module ${CMAKE_CURRENT_SOURCE_DIR}/tools/windows_files.py)
  set_tests_properties(windows_file_fixture PROPERTIES TIMEOUT 60)
endif()
add_test(NAME llm_cost_ledger COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/llm_cost_ledger.py)
set_tests_properties(llm_cost_ledger PROPERTIES TIMEOUT 30)
add_test(NAME ctest_report_validation COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/ctest_report_validation.py)
add_test(NAME owned_device_contract COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/device_contract.py $<TARGET_FILE:nex>)
set_tests_properties(owned_device_contract PROPERTIES TIMEOUT 300)
add_test(NAME sdk_operator_notices COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/sdk_notices.py)
add_test(NAME native_tool_arguments COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_tools.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_native_staging_probe>)
set_tests_properties(native_tool_arguments PROPERTIES TIMEOUT 600)
add_test(NAME parallel_mapping COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/parallel.py $<TARGET_FILE:nex>)
set_tests_properties(parallel_mapping PROPERTIES TIMEOUT 1200)
add_test(NAME result_propagation COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/propagation.py $<TARGET_FILE:nex>)
set_tests_properties(result_propagation PROPERTIES TIMEOUT 1200)
add_test(NAME compute_contract COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/compute.py $<TARGET_FILE:nex>)
set_tests_properties(compute_contract PROPERTIES TIMEOUT 1200)
add_test(NAME model_contract COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/model.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR})
set_tests_properties(model_contract PROPERTIES TIMEOUT 1200)
add_test(NAME discovery COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/discovery.py $<TARGET_FILE:nex>)
set_tests_properties(discovery PROPERTIES TIMEOUT 120)
add_test(NAME project_packaging COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/project_packaging.py $<TARGET_FILE:nex> ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(project_packaging PROPERTIES COST 100 TIMEOUT 1200)
add_test(NAME project_foreign_packaging COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/project_foreign_packaging.py $<TARGET_FILE:nex>)
set_tests_properties(project_foreign_packaging PROPERTIES COST 180 TIMEOUT 1800)
add_test(NAME native_images COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_images.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_native_staging_probe>)
set_tests_properties(native_images PROPERTIES COST 100 TIMEOUT 1200)
add_test(NAME native_staging COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_staging.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_native_staging_probe>)
set_tests_properties(native_staging PROPERTIES COST 90 TIMEOUT 1200)
add_test(NAME native_plan COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_plan.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_native_plan_probe>)
set_tests_properties(native_plan PROPERTIES COST 10 TIMEOUT 120)
add_test(NAME frontend_io COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/frontend_io.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_native_plan_probe>)
set_tests_properties(frontend_io PROPERTIES COST 10 TIMEOUT 120)
add_test(NAME project_build COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/project_build.py $<TARGET_FILE:nex>)
add_executable(nex_task_provider_profile_report_probe tests/task_provider_profile_report.cpp src/task_profile_report.cpp)
target_link_libraries(nex_task_provider_profile_report_probe PRIVATE nex_native_backend nex_frontend)
target_compile_options(nex_task_provider_profile_report_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_provider_profile_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_provider_profile.py $<TARGET_FILE:nex> --report-probe $<TARGET_FILE:nex_task_provider_profile_report_probe> ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(task_provider_profile_native PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME task_provider_debugging_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_provider_debugging.py $<TARGET_FILE:nex> ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(task_provider_debugging_native PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME task_provider_profile_lifetime_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_provider_profile_lifetime.py $<TARGET_FILE:nex> ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_provider_profile_lifetime.cpp)
set_tests_properties(task_provider_profile_lifetime_native PROPERTIES COST 60 TIMEOUT 300)
add_test(NAME task_provider_debug_lifetime_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_provider_debug_lifetime.py $<TARGET_FILE:nex> ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_provider_debug_lifetime.cpp)
set_tests_properties(task_provider_debug_lifetime_native PROPERTIES COST 60 TIMEOUT 300)

add_test(NAME task_static_provider_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_static_provider.py $<TARGET_FILE:nex> ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(task_static_provider_native PROPERTIES COST 60 TIMEOUT 1200)

add_test(NAME task_shared_provider_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_shared_provider.py $<TARGET_FILE:nex> ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(task_shared_provider_native PROPERTIES COST 60 TIMEOUT 1200)

add_test(NAME task_shared_provider_lifetime_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_shared_provider_lifetime.py $<TARGET_FILE:nex> ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_shared_provider_lifetime.cpp)
set_tests_properties(task_shared_provider_lifetime_native PROPERTIES COST 60 TIMEOUT 300)
add_test(NAME project_actions COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/project_actions.py $<TARGET_FILE:nex>)
add_test(NAME project_tasks COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/project_tasks.py $<TARGET_FILE:nex>)
add_test(NAME project_package_tasks COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/project_package_tasks.py $<TARGET_FILE:nex> ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(project_package_tasks PROPERTIES COST 60 TIMEOUT 1800)
set_tests_properties(project_tasks PROPERTIES COST 60 TIMEOUT 1800)
set_tests_properties(project_actions PROPERTIES COST 60 TIMEOUT 1200)
set_tests_properties(project_build PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME windows_runtime COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/windows_runtime.py $<TARGET_FILE:nex>)
set_tests_properties(windows_runtime PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME wasm COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/wasm.py $<TARGET_FILE:nex>)
set_tests_properties(wasm PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME editor COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/editor.py $<TARGET_FILE:nex>)
add_test(NAME language_server COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/lsp.py $<TARGET_FILE:nex>)
add_test(NAME editor_language_client COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/editor_lsp.py $<TARGET_FILE:nex>)
set_tests_properties(editor_language_client PROPERTIES TIMEOUT 120)
set_tests_properties(language_server PROPERTIES TIMEOUT 180)
set_tests_properties(editor PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME native_pages COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_pages.py $<TARGET_FILE:nex>)
set_tests_properties(native_pages PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME debug_image COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/debug_image.py $<TARGET_FILE:nex>)
set_tests_properties(debug_image PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME core_dump COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/core_dump.py $<TARGET_FILE:nex>)
set_tests_properties(core_dump PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME core_capsules COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/core_capsules.py $<TARGET_FILE:nex>)
set_tests_properties(core_capsules PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME traits COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/traits.py $<TARGET_FILE:nex>)
set_tests_properties(traits PROPERTIES COST 60 TIMEOUT 1200)
add_executable(nex_constructor_types_probe tests/constructor_types.cpp)
target_link_libraries(nex_constructor_types_probe PRIVATE nex_frontend)
add_test(NAME constructor_types_native COMMAND nex_constructor_types_probe)
add_executable(nex_task_frontend_probe tests/task_frontend.cpp src/typescript.cpp)
target_link_libraries(nex_task_frontend_probe PRIVATE nex_native_backend)
target_compile_options(nex_task_frontend_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_frontend_native COMMAND nex_task_frontend_probe ${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/language-0.18-task-names.json)
add_executable(nex_task_lifetime_probe tests/task_lifetime_probe.cpp)
target_link_libraries(nex_task_lifetime_probe PRIVATE nex_frontend)
target_compile_options(nex_task_lifetime_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_lifetime_native COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_lifetime.py $<TARGET_FILE:nex_task_lifetime_probe> $<TARGET_FILE:nex_task_reference_probe> $<TARGET_FILE:nex>)
add_executable(nex_task_migration_probe tests/task_migration_probe.cpp src/project.cpp src/graph_store.cpp src/operation_store.cpp src/change_store.cpp runtime/runtime.cpp)
target_include_directories(nex_task_migration_probe PRIVATE runtime)
target_compile_definitions(nex_task_migration_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_VERSION="${PROJECT_VERSION}" NEX_BUILD_ID="${NEX_BUILD_ID}")
target_link_libraries(nex_task_migration_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_migration_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_migration_native COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_migration.py $<TARGET_FILE:nex_task_migration_probe> $<TARGET_FILE:nex>)
add_test(NAME task_application_native COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_application.py $<TARGET_FILE:nex>)
set_tests_properties(task_application_native PROPERTIES TIMEOUT 1200)
add_executable(nex_task_application_runtime_probe tests/task_application_runtime.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_frame.cpp runtime/nex_task_application.cpp)
target_include_directories(nex_task_application_runtime_probe PRIVATE runtime)
target_compile_definitions(nex_task_application_runtime_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_link_libraries(nex_task_application_runtime_probe PRIVATE Threads::Threads)
add_test(NAME task_application_runtime COMMAND nex_task_application_runtime_probe)
add_executable(nex_task_http_request_probe tests/task_http_request.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_frame.cpp runtime/nex_task_application.cpp)
target_include_directories(nex_task_http_request_probe PRIVATE runtime)
target_compile_definitions(nex_task_http_request_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(nex_task_http_request_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_task_http_request_probe PRIVATE Threads::Threads)
add_test(NAME task_http_request_host COMMAND nex_task_http_request_probe)
set_tests_properties(task_http_request_host PROPERTIES TIMEOUT 120)
add_test(NAME task_http_request_compiled COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_http_compiled.py $<TARGET_FILE:nex>)
set_tests_properties(task_http_request_compiled PROPERTIES TIMEOUT 300)
add_test(NAME task_http_server COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_http_server.py $<TARGET_FILE:nex>)
set_tests_properties(task_http_server PROPERTIES TIMEOUT 600)
add_executable(nex_task_limits_runtime_probe tests/task_limits_runtime.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_frame.cpp runtime/nex_task_application.cpp)
target_include_directories(nex_task_limits_runtime_probe PRIVATE runtime)
target_compile_definitions(nex_task_limits_runtime_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_link_libraries(nex_task_limits_runtime_probe PRIVATE Threads::Threads)
add_test(NAME task_limits_runtime COMMAND nex_task_limits_runtime_probe)
add_test(NAME task_limits_native COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_limits_native.py $<TARGET_FILE:nex>)
set_tests_properties(task_limits_native PROPERTIES TIMEOUT 600)
add_executable(nex_task_typescript_public_probe tests/task_typescript_public.cpp src/typescript.cpp src/web.cpp src/task_process.cpp)
target_link_libraries(nex_task_typescript_public_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_include_directories(nex_task_typescript_public_probe PRIVATE runtime)
target_compile_options(nex_task_typescript_public_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_typescript_public COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_typescript_public.py $<TARGET_FILE:nex_task_typescript_public_probe> $<TARGET_FILE:nex_task_reference_probe> --compiler $<TARGET_FILE:nex>)
set_tests_properties(task_typescript_public PROPERTIES TIMEOUT 600)
add_executable(nex_task_ir_probe tests/task_ir.cpp)
target_include_directories(nex_task_ir_probe PRIVATE runtime)
target_link_libraries(nex_task_ir_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_ir_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_ir_native COMMAND nex_task_ir_probe)
add_executable(nex_task_ast_probe tests/task_ast.cpp)
target_include_directories(nex_task_ast_probe PRIVATE runtime)
target_link_libraries(nex_task_ast_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_ast_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_ast_native COMMAND nex_task_ast_probe)
add_executable(nex_task_reference_probe tests/task_reference.cpp runtime/runtime.cpp)
target_include_directories(nex_task_reference_probe PRIVATE runtime)
target_compile_definitions(nex_task_reference_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_link_libraries(nex_task_reference_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_reference_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_reference_native COMMAND nex_task_reference_probe)
add_executable(nex_task_reference_limits_probe tests/task_reference_limits.cpp runtime/runtime.cpp)
target_include_directories(nex_task_reference_limits_probe PRIVATE runtime)
target_compile_definitions(nex_task_reference_limits_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_link_libraries(nex_task_reference_limits_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_reference_limits_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_limits_reference COMMAND nex_task_reference_limits_probe)

add_test(NAME string_debug COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/string_debug.py $<TARGET_FILE:nex>)
add_test(NAME string_debug_provider COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/string_debug_provider.py ${CMAKE_CURRENT_SOURCE_DIR}/debug/lldb_nex.py)
set_tests_properties(string_debug PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME graph_queries COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/graph_queries.py $<TARGET_FILE:nex>)
set_tests_properties(graph_queries PROPERTIES COST 60 TIMEOUT 1200)
add_executable(nex_frontend_diagnostics_probe tests/frontend_diagnostics.cpp)
target_link_libraries(nex_frontend_diagnostics_probe PRIVATE nex_frontend)
add_test(NAME frontend_diagnostics_native COMMAND nex_frontend_diagnostics_probe)
add_test(NAME frontend_diagnostics COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/frontend_diagnostics.py $<TARGET_FILE:nex>)
set_tests_properties(frontend_diagnostics PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME project_versions COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/project_versions.py $<TARGET_FILE:nex>)
set_tests_properties(project_versions PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME graph_snapshots COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/graph_snapshots.py $<TARGET_FILE:nex>)
set_tests_properties(graph_snapshots PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME change_history COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/change_history.py $<TARGET_FILE:nex>)
set_tests_properties(change_history PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME operation_patches COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/operation_patches.py $<TARGET_FILE:nex>)
set_tests_properties(operation_patches PROPERTIES COST 60 TIMEOUT 1200)
add_test(NAME native_arithmetic COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_arithmetic.py $<TARGET_FILE:nex>)
set_tests_properties(native_arithmetic PROPERTIES COST 90 TIMEOUT 1200)
add_executable(nex_native_sites_probe tests/native_sites_runtime.cpp runtime/runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_native_sites_probe PRIVATE runtime)
target_compile_options(nex_native_sites_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_native_sites_probe PRIVATE Threads::Threads)
add_test(NAME native_sites_runtime COMMAND nex_native_sites_probe)
add_executable(nex_source_error_native_packet_probe tests/source_error_native_packet.cpp runtime/runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_source_error_native_packet_probe PRIVATE runtime)
target_compile_definitions(nex_source_error_native_packet_probe PRIVATE NEX_PROFILE_ENABLED)
target_link_libraries(nex_source_error_native_packet_probe PRIVATE Threads::Threads)
target_compile_options(nex_source_error_native_packet_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME source_error_native_packet COMMAND nex_source_error_native_packet_probe)
set_tests_properties(source_error_native_packet PROPERTIES TIMEOUT 60)
add_executable(nex_application_ownership_probe tests/application_ownership.cpp runtime/runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_application_ownership_probe PRIVATE runtime)
target_compile_definitions(nex_application_ownership_probe PRIVATE NEX_PROFILE_ENABLED)
target_compile_options(nex_application_ownership_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_application_ownership_probe PRIVATE Threads::Threads)
add_test(NAME application_ownership_runtime COMMAND nex_application_ownership_probe)
add_test(NAME native_diagnostics COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_diagnostics.py $<TARGET_FILE:nex>)
set_tests_properties(native_diagnostics PROPERTIES COST 60 TIMEOUT 1200)

add_test(NAME source_ffi COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_ffi.py $<TARGET_FILE:nex>)
add_test(NAME task_foreign COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_foreign.py $<TARGET_FILE:nex>)
set_tests_properties(task_foreign PROPERTIES COST 240 TIMEOUT 1800)
add_test(NAME resources COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/resources.py $<TARGET_FILE:nex>)
add_test(NAME resource_debug COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/resource_debug.py $<TARGET_FILE:nex>)
add_test(NAME sdk_archives COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/sdk_archives.py)
add_test(NAME provider_preparation_source COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/provider_preparation.py $<TARGET_FILE:nex>)
set_tests_properties(provider_preparation_source PROPERTIES TIMEOUT 180)
add_test(NAME packaging COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/packaging.py $<TARGET_FILE:nex>)
add_test(NAME foreign_packaging COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/foreign_packaging.py $<TARGET_FILE:nex>)
set_tests_properties(foreign_packaging PROPERTIES COST 180 TIMEOUT 1800)
find_package(Threads REQUIRED)
add_executable(nex_owned_functions_probe tests/owned_functions.cpp runtime/runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_owned_functions_probe PRIVATE runtime)
target_compile_definitions(nex_owned_functions_probe PRIVATE NEX_PROFILE_ENABLED NEX_STRUCTURED_WORKERS)
target_compile_options(nex_owned_functions_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_owned_functions_probe PRIVATE Threads::Threads)
add_test(NAME owned_functions_runtime COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/owned_functions.py $<TARGET_FILE:nex_owned_functions_probe>)
set_tests_properties(owned_functions_runtime PROPERTIES TIMEOUT 60)
add_executable(nex_structured_workers_probe tests/structured_workers.cpp runtime/runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_structured_workers_probe PRIVATE runtime)
target_compile_definitions(nex_structured_workers_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_PROFILE_ENABLED)
target_compile_options(nex_structured_workers_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_structured_workers_probe PRIVATE Threads::Threads)
add_test(NAME structured_workers_runtime COMMAND nex_structured_workers_probe)
set_tests_properties(structured_workers_runtime PROPERTIES TIMEOUT 30)
add_executable(nex_task_scheduler_probe tests/task_scheduler.cpp runtime/runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_task_scheduler_probe PRIVATE runtime)
target_compile_definitions(nex_task_scheduler_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_PROFILE_ENABLED)
target_compile_options(nex_task_scheduler_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_task_scheduler_probe PRIVATE Threads::Threads)
add_test(NAME task_scheduler_runtime COMMAND nex_task_scheduler_probe)
set_tests_properties(task_scheduler_runtime PROPERTIES TIMEOUT 45)
add_test(NAME compiled_workers_native COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/compiled_workers.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_native_staging_probe>)
set_tests_properties(compiled_workers_native PROPERTIES TIMEOUT 300)
if(APPLE OR CMAKE_SYSTEM_NAME STREQUAL "Linux")
  add_executable(nex_task_process_probe tests/task_process.cpp src/task_process.cpp)
  target_link_libraries(nex_task_process_probe PRIVATE nex_frontend Threads::Threads)
  if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_compile_definitions(nex_task_process_probe PRIVATE NEX_TASK_PROCESS_TEST_FORK=1)
  endif()
  add_test(NAME task_process_native COMMAND nex_task_process_probe)
  set_tests_properties(task_process_native PROPERTIES TIMEOUT 30)
endif()
add_library(nex_foreign_test_module MODULE tests/foreign_module.c)
target_include_directories(nex_foreign_test_module PRIVATE runtime)
set_target_properties(nex_foreign_test_module PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_VISIBILITY_PRESET hidden)
add_executable(nex_foreign_scope_probe tests/foreign_scope.cpp runtime/nex_foreign.cpp runtime/foreign_runtime.cpp runtime/runtime.cpp runtime/nex_ffi_loader.cpp runtime/nex_ffi.cpp runtime/nex_ffi_types.cpp runtime/nex_ffi_resources.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp runtime/nex_resource_executor.cpp runtime/nex_files.cpp runtime/nex_json.cpp)
target_include_directories(nex_foreign_scope_probe PRIVATE runtime)
target_compile_options(nex_foreign_scope_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_foreign_scope_probe PRIVATE Threads::Threads OpenSSL::Crypto ${CMAKE_DL_LIBS})
add_dependencies(nex_foreign_scope_probe nex_foreign_test_module)
add_test(NAME foreign_scope_native COMMAND nex_foreign_scope_probe $<TARGET_FILE:nex_foreign_test_module>)
set_tests_properties(foreign_scope_native PROPERTIES TIMEOUT 120)
add_library(nex_ffi_test_module MODULE tests/ffi_module.c)
add_library(nex_ffi_test_missing MODULE tests/ffi_module.c)
add_library(nex_ffi_executable_module MODULE tests/ffi_executable_module.c)
target_include_directories(nex_ffi_executable_module PRIVATE runtime)
target_link_libraries(nex_ffi_executable_module PRIVATE ${CMAKE_DL_LIBS})
set_target_properties(nex_ffi_executable_module PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_VISIBILITY_PRESET hidden)
add_executable(nex_ffi_executable_worker tests/ffi_executable_worker.c)
target_compile_definitions(nex_ffi_test_missing PRIVATE NEX_FFI_TEST_NO_ENTRY)
foreach(NEX_FFI_MODULE_TARGET nex_ffi_test_module nex_ffi_test_missing)
  target_include_directories(${NEX_FFI_MODULE_TARGET} PRIVATE runtime)
  set_target_properties(${NEX_FFI_MODULE_TARGET} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_VISIBILITY_PRESET hidden)
endforeach()
add_executable(nex_ffi_loader_probe tests/ffi_loader.cpp runtime/nex_ffi_loader.cpp runtime/nex_ffi.cpp runtime/nex_ffi_types.cpp runtime/nex_ffi_resources.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp runtime/nex_resource_executor.cpp runtime/nex_files.cpp runtime/nex_json.cpp)
target_include_directories(nex_ffi_loader_probe PRIVATE runtime)
target_compile_options(nex_ffi_loader_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_ffi_loader_probe PRIVATE Threads::Threads OpenSSL::Crypto ${CMAKE_DL_LIBS})
add_dependencies(nex_ffi_loader_probe nex_ffi_test_module nex_ffi_test_missing nex_ffi_executable_module nex_ffi_executable_worker)
add_test(NAME ffi_loader_native COMMAND nex_ffi_loader_probe $<TARGET_FILE:nex_ffi_test_module> $<TARGET_FILE:nex_ffi_test_missing> $<TARGET_FILE:nex_ffi_executable_module> $<TARGET_FILE:nex_ffi_executable_worker>)
set_tests_properties(ffi_loader_native PROPERTIES TIMEOUT 120)
add_executable(nex_ffi_runtime_probe tests/ffi_runtime.cpp tests/ffi_producer.c runtime/nex_ffi.cpp runtime/nex_ffi_types.cpp runtime/nex_ffi_resources.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp runtime/nex_resource_executor.cpp runtime/nex_files.cpp runtime/nex_json.cpp)
set_source_files_properties(tests/ffi_producer.c PROPERTIES INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/ffi-0.37")
target_include_directories(nex_ffi_runtime_probe PRIVATE runtime)
target_compile_options(nex_ffi_runtime_probe PRIVATE -Wall -Wextra -Wpedantic)
set_target_properties(nex_ffi_runtime_probe PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
target_link_libraries(nex_ffi_runtime_probe PRIVATE Threads::Threads)
add_test(NAME ffi_runtime_native COMMAND nex_ffi_runtime_probe)
set_tests_properties(ffi_runtime_native PROPERTIES TIMEOUT 60)
add_executable(nex_ffi_typed_probe tests/ffi_typed.cpp examples/ffi/producer.c runtime/nex_ffi.cpp runtime/nex_ffi_types.cpp runtime/nex_ffi_resources.cpp runtime/nex_external_resource.cpp runtime/nex_resource_region.cpp runtime/nex_resource_executor.cpp runtime/nex_files.cpp runtime/nex_json.cpp)
target_include_directories(nex_ffi_typed_probe PRIVATE runtime)
target_compile_options(nex_ffi_typed_probe PRIVATE -Wall -Wextra -Wpedantic)
set_target_properties(nex_ffi_typed_probe PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
target_link_libraries(nex_ffi_typed_probe PRIVATE Threads::Threads)
add_test(NAME ffi_typed_native COMMAND nex_ffi_typed_probe)
set_tests_properties(ffi_typed_native PROPERTIES TIMEOUT 60)
include(experiments/typed-resources/probes.cmake)
add_test(NAME ffi_types COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/ffi_types.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_ffi_typed_probe>)
add_executable(nex_resource_values_probe tests/resource_values.cpp runtime/runtime.cpp runtime/nex_json.cpp runtime/nex_files.cpp runtime/files_runtime.cpp)
target_include_directories(nex_resource_values_probe PRIVATE runtime)
target_compile_definitions(nex_resource_values_probe PRIVATE NEX_PROFILE_ENABLED)
target_compile_options(nex_resource_values_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_resource_values_probe PRIVATE Threads::Threads)
add_test(NAME resource_values_native COMMAND nex_resource_values_probe)
set_tests_properties(resource_values_native PROPERTIES TIMEOUT 60)
add_executable(nex_resources_runtime_probe tests/resources_runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_resources_runtime_probe PRIVATE runtime)
target_compile_options(nex_resources_runtime_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_resources_runtime_probe PRIVATE Threads::Threads)
add_test(NAME resources_runtime_native COMMAND nex_resources_runtime_probe)
set_tests_properties(resources_runtime_native PROPERTIES TIMEOUT 60)
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
add_test(NAME graph_identities COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/graph_identities.py $<TARGET_FILE:nex>)
add_test(NAME type_patches COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/type_patches.py $<TARGET_FILE:nex>)
add_test(NAME dap_transport COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/dap_transport.py $<TARGET_FILE:nex>)
add_test(NAME incremental COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/incremental.py $<TARGET_FILE:nex>)
add_test(NAME native_targets COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_targets.py $<TARGET_FILE:nex>)
add_test(NAME windows_targets COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/windows_targets.py $<TARGET_FILE:nex>)
set_tests_properties(windows_targets PROPERTIES TIMEOUT 1200)
add_test(NAME platform_compiler_cohort COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/platform_cohort.py $<TARGET_FILE:nex>)
add_test(NAME native_entry_abi COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_entry_abi.py $<TARGET_FILE:nex>)
set_tests_properties(native_entry_abi PROPERTIES TIMEOUT 900)
install(FILES tests/native_entry_abi.py DESTINATION share/nex/tests)
add_test(NAME ios_targets COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/ios_targets.py $<TARGET_FILE:nex>)
add_test(NAME mobile_projects COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/mobile_projects.py)
add_test(NAME sdk_host COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/sdk_host.py $<TARGET_FILE:nex>)
add_test(NAME profiling COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/profiling.py $<TARGET_FILE:nex>)
add_test(NAME server_workload COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/server_workload.py $<TARGET_FILE:nex>)
set_tests_properties(server_workload PROPERTIES COST 180 TIMEOUT 900)
add_test(NAME server_debug COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/server_debug.py $<TARGET_FILE:nex>)
set_tests_properties(server_debug PROPERTIES COST 100 TIMEOUT 900)
add_test(NAME task_workloads COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_workloads.py $<TARGET_FILE:nex>)
set_tests_properties(task_workloads PROPERTIES COST 180 TIMEOUT 1200)
add_test(NAME verification COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/verification.py $<TARGET_FILE:nex>)
add_test(NAME runtime_contracts COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/runtime_contracts.py $<TARGET_FILE:nex>)
set_tests_properties(runtime_contracts PROPERTIES TIMEOUT 900)
add_test(NAME runtime_loop_contracts COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/runtime_loop_contracts.py $<TARGET_FILE:nex>)
set_tests_properties(runtime_loop_contracts PROPERTIES TIMEOUT 1200)
add_test(NAME runtime_value_contracts COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/runtime_value_contracts.py $<TARGET_FILE:nex>)
set_tests_properties(runtime_value_contracts PROPERTIES TIMEOUT 1200)
add_test(NAME runtime_generic_contracts COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/runtime_generic_contracts.py $<TARGET_FILE:nex>)
set_tests_properties(runtime_generic_contracts PROPERTIES TIMEOUT 1200)
install(FILES tests/runtime_contracts.py tests/runtime_loop_contracts.py tests/runtime_value_contracts.py tests/runtime_generic_contracts.py DESTINATION share/nex/tests)
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
  add_test(NAME web_workers COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/web_workers.py $<TARGET_FILE:nex>)
  set_tests_properties(web PROPERTIES ENVIRONMENT "NEX_NODE=${NEX_NODE_EXECUTABLE}")
  set_tests_properties(web_commands PROPERTIES ENVIRONMENT "NEX_NODE=${NEX_NODE_EXECUTABLE}")
  set_tests_properties(web_workers PROPERTIES ENVIRONMENT "NEX_NODE=${NEX_NODE_EXECUTABLE}")
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

add_test(NAME task_limits_workflow COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_limits_workflow.py $<TARGET_FILE:nex>)
set_tests_properties(task_limits_workflow PROPERTIES TIMEOUT 900)

add_executable(nex_file_read_lease_probe tests/file_read_lease.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp)
target_compile_definitions(nex_file_read_lease_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_file_read_lease_probe PRIVATE runtime)
target_link_libraries(nex_file_read_lease_probe PRIVATE Threads::Threads)
add_test(NAME task_external_file_lease COMMAND nex_file_read_lease_probe)
set_tests_properties(task_external_file_lease PROPERTIES TIMEOUT 60)

add_executable(nex_task_file_write_host_probe tests/task_file_write_host.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp)
target_compile_definitions(nex_task_file_write_host_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_task_file_write_host_probe PRIVATE runtime)
target_link_libraries(nex_task_file_write_host_probe PRIVATE Threads::Threads)
target_compile_options(nex_task_file_write_host_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_external_file_write_host COMMAND nex_task_file_write_host_probe)
set_tests_properties(task_external_file_write_host PROPERTIES TIMEOUT 120)
add_executable(nex_task_file_stream_host_probe tests/task_file_stream_host.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp)
target_compile_definitions(nex_task_file_stream_host_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_task_file_stream_host_probe PRIVATE runtime)
target_link_libraries(nex_task_file_stream_host_probe PRIVATE Threads::Threads)
target_compile_options(nex_task_file_stream_host_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_external_file_stream_host COMMAND nex_task_file_stream_host_probe)
set_tests_properties(task_external_file_stream_host PROPERTIES TIMEOUT 120)
add_test(NAME task_file_stream_source_boundaries COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_boundaries.py $<TARGET_FILE:nex> --retained-probe $<TARGET_FILE:nex_task_stream_source_probe>)
set_tests_properties(task_file_stream_source_boundaries PROPERTIES TIMEOUT 600)
install(FILES tools/sdk_task_streams.py DESTINATION share/nex/tools)
install(FILES tests/task_file_stream_host.cpp DESTINATION share/nex/tools RENAME task_file_stream_host_acceptance.cpp)

add_executable(nex_task_file_regions_probe tests/task_file_regions.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp)
target_compile_definitions(nex_task_file_regions_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_task_file_regions_probe PRIVATE runtime)
target_link_libraries(nex_task_file_regions_probe PRIVATE Threads::Threads)
add_test(NAME task_file_regions_host COMMAND nex_task_file_regions_probe)
set_tests_properties(task_file_regions_host PROPERTIES TIMEOUT 120)
add_executable(nex_task_stream_source_probe tests/task_stream_source_probe.cpp src/typescript.cpp)
target_link_libraries(nex_task_stream_source_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
add_test(NAME task_file_stream_source COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_source.py $<TARGET_FILE:nex_task_stream_source_probe>)
add_test(NAME task_file_stream_requirements COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_requirements.py $<TARGET_FILE:nex_task_stream_source_probe>)
set_tests_properties(task_file_stream_requirements PROPERTIES TIMEOUT 900)
add_test(NAME task_file_stream_control COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_control.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_task_stream_source_probe>)
add_executable(nex_task_stream_inflight_probe tests/task_stream_inflight_probe.cpp)
target_link_libraries(nex_task_stream_inflight_probe PRIVATE nex_frontend Threads::Threads)
target_include_directories(nex_task_stream_inflight_probe PRIVATE runtime)
target_compile_definitions(nex_task_stream_inflight_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(nex_task_stream_inflight_probe PRIVATE -Wall -Wextra -Wpedantic)
add_executable(nex_file_io_observation_probe tests/file_io_observation.cpp)
target_link_libraries(nex_file_io_observation_probe PRIVATE nex_frontend Threads::Threads)
target_include_directories(nex_file_io_observation_probe PRIVATE runtime)
target_compile_options(nex_file_io_observation_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME file_io_observation COMMAND nex_file_io_observation_probe)
set_tests_properties(file_io_observation PROPERTIES TIMEOUT 60)
add_test(NAME task_marker_record COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_marker_record.py)
set_tests_properties(task_marker_record PROPERTIES TIMEOUT 30)
add_test(NAME public_task_stream_histories COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_cli_histories.py $<TARGET_FILE:nex>)
set_tests_properties(public_task_stream_histories PROPERTIES TIMEOUT 3600)
install(FILES tests/task_stream_delivery.py tests/task_stream_cli_histories.py tests/task_stream_ffi_fixture.py DESTINATION share/nex/tests)
file(GLOB NEX_TASK_STREAM_MIGRATION_FIXTURES CONFIGURE_DEPENDS tests/fixtures/language-0.23-sdk1335-stream-*.json tests/fixtures/language-0.23-sdk1335-stream-*.sql tests/fixtures/language-0.23-sdk1335-mixed-*.json tests/fixtures/language-0.23-sdk1335-mixed-*.sql)
install(FILES ${NEX_TASK_STREAM_MIGRATION_FIXTURES} DESTINATION share/nex/examples/task-stream-migration)
add_test(NAME public_task_stream_delivery COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_delivery.py $<TARGET_FILE:nex>)
set_tests_properties(public_task_stream_delivery PROPERTIES TIMEOUT 1800)
add_test(NAME task_file_stream_inflight COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_inflight.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_task_stream_source_probe> $<TARGET_FILE:nex_task_stream_inflight_probe>)
set_tests_properties(task_file_stream_inflight PROPERTIES TIMEOUT 1800)
set_tests_properties(task_file_stream_control PROPERTIES TIMEOUT 1800)
set_tests_properties(task_file_stream_source PROPERTIES TIMEOUT 1800)
add_executable(nex_task_write_source_probe tests/task_write_source_probe.cpp src/typescript.cpp)
add_executable(nex_task_write_provider_probe tests/task_write_provider_probe.cpp src/native_images.cpp)
add_executable(nex_task_stream_provider_probe tests/task_stream_provider_probe.cpp src/native_images.cpp)
target_link_libraries(nex_task_stream_provider_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_definitions(nex_task_stream_provider_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME task_stream_provider_boundary COMMAND nex_task_stream_provider_probe boundary)
add_test(NAME task_stream_provider COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_provider.py $<TARGET_FILE:nex_task_stream_provider_probe>)
set_tests_properties(task_stream_provider PROPERTIES TIMEOUT 2400)
target_link_libraries(nex_task_write_provider_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_definitions(nex_task_write_provider_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME task_write_provider_boundary COMMAND nex_task_write_provider_probe boundary)
add_test(NAME task_write_provider COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_write_provider.py $<TARGET_FILE:nex_task_write_provider_probe>)
set_tests_properties(task_write_provider PROPERTIES TIMEOUT 1800)
add_test(NAME public_task_write_delivery COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_write_delivery.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(public_task_write_delivery PROPERTIES TIMEOUT 2400)
install(FILES tests/task_write_delivery.py DESTINATION share/nex/tests)
install(FILES tests/fixtures/language-0.22-sdk131-task-writes.json tests/fixtures/language-0.22-sdk131-task-writes.sql DESTINATION share/nex/examples/task-write-migration)
add_test(NAME public_task_write_histories COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_write_histories.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR})
set_tests_properties(public_task_write_histories PROPERTIES TIMEOUT 2400)
add_test(NAME public_task_write_observability COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_write_observability.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR})
set_tests_properties(public_task_write_observability PROPERTIES TIMEOUT 1200)
install(FILES tests/task_write_histories.py DESTINATION share/nex/tests)
install(FILES tests/fixtures/language-0.22-sdk1326-README.md DESTINATION share/nex/examples/task-write-history RENAME README.md)
install(FILES
  tests/fixtures/language-0.22-sdk1326-resources.json tests/fixtures/language-0.22-sdk1326-resources.sql
  tests/fixtures/language-0.22-sdk1326-nominal.json tests/fixtures/language-0.22-sdk1326-nominal.sql
  tests/fixtures/language-0.22-sdk1326-callable.json tests/fixtures/language-0.22-sdk1326-callable.sql
  tests/fixtures/language-0.22-sdk1326-imports.json tests/fixtures/language-0.22-sdk1326-imports.sql
  tests/fixtures/language-0.22-sdk1326-tasks.json tests/fixtures/language-0.22-sdk1326-tasks.sql
  tests/fixtures/language-0.22-sdk1326-model-compute-device-imports.json tests/fixtures/language-0.22-sdk1326-model-compute-device-imports.sql.xz.b85
  DESTINATION share/nex/examples/task-write-history)
target_link_libraries(nex_task_write_source_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
add_executable(nex_task_stream_migration_probe tests/task_stream_migration_probe.cpp src/project.cpp src/graph_store.cpp src/operation_store.cpp src/change_store.cpp)
target_link_libraries(nex_task_stream_migration_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
add_test(NAME task_file_stream_migration COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_migration.py $<TARGET_FILE:nex_task_stream_migration_probe> $<TARGET_FILE:nex>)
set_tests_properties(task_file_stream_migration PROPERTIES TIMEOUT 1200)
add_test(NAME task_file_stream_histories COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_histories.py $<TARGET_FILE:nex_task_stream_migration_probe> $<TARGET_FILE:nex> $<TARGET_FILE:nex_source_resource_probe>)
set_tests_properties(task_file_stream_histories PROPERTIES TIMEOUT 1800)
add_test(NAME task_file_stream_ffi_histories COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_stream_ffi_histories.py $<TARGET_FILE:nex_task_stream_migration_probe> $<TARGET_FILE:nex> $<TARGET_FILE:nex_source_resource_probe>)
set_tests_properties(task_file_stream_ffi_histories PROPERTIES TIMEOUT 2400)
target_compile_definitions(nex_task_stream_migration_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_VERSION="${PROJECT_VERSION}" NEX_BUILD_ID="${NEX_BUILD_ID}")
add_executable(nex_task_write_migration_probe tests/task_write_migration_probe.cpp src/project.cpp src/graph_store.cpp src/operation_store.cpp src/change_store.cpp)
target_link_libraries(nex_task_write_migration_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_definitions(nex_task_write_migration_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_VERSION="${PROJECT_VERSION}" NEX_BUILD_ID="${NEX_BUILD_ID}")
target_compile_options(nex_task_write_migration_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_write_migration COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_write_migration.py $<TARGET_FILE:nex_task_write_migration_probe> $<TARGET_FILE:nex>)
set_tests_properties(task_write_migration PROPERTIES TIMEOUT 1200)
add_executable(nex_task_stream_protocol_probe tests/task_stream_protocol.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_task_frame.cpp)
target_compile_definitions(nex_task_stream_protocol_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_task_stream_protocol_probe PRIVATE runtime)
target_link_libraries(nex_task_stream_protocol_probe PRIVATE Threads::Threads)
add_test(NAME task_file_stream_protocol COMMAND nex_task_stream_protocol_probe)

add_executable(nex_task_file_cleanup_probe tests/task_file_cleanup.cpp runtime/runtime.cpp runtime/nex_files.cpp)
target_include_directories(nex_task_file_cleanup_probe PRIVATE runtime)
target_link_libraries(nex_task_file_cleanup_probe PRIVATE Threads::Threads)
add_test(NAME task_file_cleanup_host COMMAND nex_task_file_cleanup_probe)
set_tests_properties(task_file_cleanup_host PROPERTIES TIMEOUT 60)
add_executable(nex_typed_task_protocol_probe tests/typed_task_protocol.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_task_frame.cpp runtime/nex_task_application.cpp runtime/nex_resource_region.cpp runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp)
target_compile_definitions(nex_typed_task_protocol_probe PRIVATE NEX_PROFILE_ENABLED NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_typed_task_protocol_probe PRIVATE runtime)
target_link_libraries(nex_typed_task_protocol_probe PRIVATE Threads::Threads)
add_test(NAME typed_task_public_protocol COMMAND nex_typed_task_protocol_probe)
set_tests_properties(typed_task_public_protocol PROPERTIES TIMEOUT 60)
add_executable(nex_typed_provider_records_probe tests/typed_provider_records.cpp)
target_link_libraries(nex_typed_provider_records_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
add_test(NAME typed_error_provider_records COMMAND nex_typed_provider_records_probe)
set_tests_properties(typed_error_provider_records PROPERTIES TIMEOUT 60)
add_test(NAME typed_error_projects COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_error_projects.py $<TARGET_FILE:nex_task_stream_project_probe> --compiler $<TARGET_FILE:nex> ${NEX_TEST_PACKAGE_NOTICES_ARGS})
set_tests_properties(typed_error_projects PROPERTIES TIMEOUT 1800)
add_test(NAME typed_error_debugging COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_error_debugging.py $<TARGET_FILE:nex_task_stream_project_probe> $<TARGET_FILE:nex>)
set_tests_properties(typed_error_debugging PROPERTIES TIMEOUT 1800 SKIP_RETURN_CODE 77)
add_test(NAME typed_web_delivery COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_web_delivery.py $<TARGET_FILE:nex_task_stream_project_probe> $<TARGET_FILE:nex_typed_source_typescript_probe> $<TARGET_FILE:nex>)
set_tests_properties(typed_web_delivery PROPERTIES TIMEOUT 1800)
add_executable(nex_task_write_protocol_probe tests/task_write_protocol.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_task_frame.cpp)
target_compile_definitions(nex_task_write_protocol_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_task_write_protocol_probe PRIVATE runtime)
target_link_libraries(nex_task_write_protocol_probe PRIVATE Threads::Threads)
add_test(NAME task_write_protocol COMMAND nex_task_write_protocol_probe)
add_test(NAME task_write_source COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_write_source.py $<TARGET_FILE:nex_task_write_source_probe>)
set_tests_properties(task_write_source PROPERTIES TIMEOUT 1200)

add_executable(nex_task_reference_external_probe tests/task_reference_external.cpp runtime/runtime.cpp)
target_include_directories(nex_task_reference_external_probe PRIVATE runtime)
target_compile_definitions(nex_task_reference_external_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_link_libraries(nex_task_reference_external_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_reference_external_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_external_reference COMMAND nex_task_reference_external_probe)
add_executable(nex_task_reference_files_probe tests/task_reference_files.cpp)
target_link_libraries(nex_task_reference_files_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_task_reference_files_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_file_reads_reference COMMAND nex_task_reference_files_probe)
set_tests_properties(task_file_reads_reference PROPERTIES TIMEOUT 120)
add_executable(nex_task_file_frontend_probe tests/task_file_frontend.cpp)
target_link_libraries(nex_task_file_frontend_probe PRIVATE nex_frontend Threads::Threads)
add_test(NAME task_file_reads_frontend COMMAND nex_task_file_frontend_probe)
add_executable(nex_task_file_reads_native_runtime_probe tests/task_file_read_native_runtime.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_task_frame.cpp runtime/nex_task_application.cpp)
target_include_directories(nex_task_file_reads_native_runtime_probe PRIVATE runtime)
target_compile_definitions(nex_task_file_reads_native_runtime_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_link_libraries(nex_task_file_reads_native_runtime_probe PRIVATE Threads::Threads)
add_test(NAME task_file_reads_native_runtime COMMAND nex_task_file_reads_native_runtime_probe)
set_tests_properties(task_file_reads_native_runtime PROPERTIES TIMEOUT 120)
add_test(NAME task_file_reads_native COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_file_reads_native.py $<TARGET_FILE:nex>)
set_tests_properties(task_file_reads_native PROPERTIES TIMEOUT 900)
add_test(NAME task_file_reads_typescript COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_typescript_files.py $<TARGET_FILE:nex_task_typescript_public_probe>)
set_tests_properties(task_file_reads_typescript PROPERTIES TIMEOUT 180)
add_test(NAME task_file_migration_native COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_file_migration.py $<TARGET_FILE:nex_task_migration_probe> $<TARGET_FILE:nex>)
set_tests_properties(task_external_reference PROPERTIES TIMEOUT 120)

add_test(NAME task_external_typescript COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_typescript_external.py $<TARGET_FILE:nex_task_typescript_public_probe>)
set_tests_properties(task_external_typescript PROPERTIES TIMEOUT 180)
target_link_libraries(nex_frontend PUBLIC Threads::Threads)

foreach(NEX_TASK_KERNEL_TARGET IN ITEMS nex_task_migration_probe nex_task_application_runtime_probe nex_task_http_request_probe nex_task_limits_runtime_probe nex_task_reference_probe nex_task_reference_limits_probe nex_task_scheduler_probe nex_task_reference_external_probe)
  target_sources(${NEX_TASK_KERNEL_TARGET} PRIVATE runtime/nex_task_external.cpp)
endforeach()
add_executable(nex_task_external_probe tests/task_external.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp)
target_include_directories(nex_task_external_probe PRIVATE runtime)
target_compile_definitions(nex_task_external_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_link_libraries(nex_task_external_probe PRIVATE Threads::Threads)
target_compile_options(nex_task_external_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_external_native COMMAND nex_task_external_probe)

# This probe exercises the collector API independently of the scheduler bridge.
add_executable(nex_task_profile_collector_probe tests/task_profile_collector.cpp runtime/nex_task_profile.cpp)
target_include_directories(nex_task_profile_collector_probe PRIVATE runtime)
target_link_libraries(nex_task_profile_collector_probe PRIVATE Threads::Threads)
target_compile_options(nex_task_profile_collector_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_profile_collector_native COMMAND nex_task_profile_collector_probe)
set_tests_properties(task_profile_collector_native PROPERTIES TIMEOUT 60)

add_executable(nex_task_profile_runtime_probe tests/task_profile_runtime.cpp
  runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp
  runtime/nex_task_frame.cpp runtime/nex_task_application.cpp
  runtime/nex_task_profile.cpp runtime/nex_profile.cpp
  runtime/third_party/tracy/public/TracyClient.cpp)
target_include_directories(nex_task_profile_runtime_probe PRIVATE runtime)
target_compile_definitions(nex_task_profile_runtime_probe PRIVATE
  NEX_PROFILE_ENABLED NEX_TASK_PROFILE_ENABLED NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS
  TRACY_ENABLE TRACY_ON_DEMAND TRACY_DELAYED_INIT TRACY_MANUAL_LIFETIME
  TRACY_ONLY_LOCALHOST TRACY_NO_BROADCAST TRACY_NO_CODE_TRANSFER TRACY_NO_CALLSTACK
  TRACY_NO_SYSTEM_TRACING TRACY_NO_SAMPLING TRACY_NO_CRASH_HANDLER TRACY_NO_FRAME_IMAGE)
target_link_libraries(nex_task_profile_runtime_probe PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
target_compile_options(nex_task_profile_runtime_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_profile_runtime_native COMMAND nex_task_profile_runtime_probe)
set_tests_properties(task_profile_runtime_native PROPERTIES TIMEOUT 120)

add_executable(nex_task_profile_registry_probe tests/task_profile_registry.cpp
  runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp
  runtime/nex_task_frame.cpp runtime/nex_task_application.cpp
  runtime/nex_task_profile.cpp runtime/nex_profile.cpp
  runtime/third_party/tracy/public/TracyClient.cpp)
target_include_directories(nex_task_profile_registry_probe PRIVATE runtime)
target_compile_definitions(nex_task_profile_registry_probe PRIVATE
  NEX_PROFILE_ENABLED NEX_TASK_PROFILE_ENABLED NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS
  TRACY_ENABLE TRACY_ON_DEMAND TRACY_DELAYED_INIT TRACY_MANUAL_LIFETIME
  TRACY_ONLY_LOCALHOST TRACY_NO_BROADCAST TRACY_NO_CODE_TRANSFER TRACY_NO_CALLSTACK
  TRACY_NO_SYSTEM_TRACING TRACY_NO_SAMPLING TRACY_NO_CRASH_HANDLER TRACY_NO_FRAME_IMAGE)
target_link_libraries(nex_task_profile_registry_probe PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
target_compile_options(nex_task_profile_registry_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_profile_registry_native COMMAND nex_task_profile_registry_probe)
set_tests_properties(task_profile_registry_native PROPERTIES TIMEOUT 120)

add_executable(nex_task_profile_report_probe tests/task_profile_report.cpp src/task_profile_report.cpp)
target_link_libraries(nex_task_profile_report_probe PRIVATE nex_native_backend nex_frontend)
target_compile_options(nex_task_profile_report_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_profile_report_native COMMAND nex_task_profile_report_probe)
set_tests_properties(task_profile_report_native PROPERTIES TIMEOUT 60)

add_test(NAME task_profile_workflow_native COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_profile_workflow.py $<TARGET_FILE:nex>)
set_tests_properties(task_profile_workflow_native PROPERTIES TIMEOUT 1800)

add_test(NAME task_profile_native COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_profile_native.py $<TARGET_FILE:nex>)
set_tests_properties(task_profile_native PROPERTIES TIMEOUT 900)

add_executable(nex_task_profile_versioned_probe tests/task_profile_versioned.cpp
  src/profiling.cpp src/task_profile_report.cpp src/task_process.cpp)
target_link_libraries(nex_task_profile_versioned_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_task_profile_versioned_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
target_compile_options(nex_task_profile_versioned_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_profile_versioned_native COMMAND nex_task_profile_versioned_probe
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/language-0.19-sdk115-tasks.json
  ${CMAKE_CURRENT_BINARY_DIR}/task-profile-versioned-evidence)
set_tests_properties(task_profile_versioned_native PROPERTIES TIMEOUT 600)
set_tests_properties(task_external_native PROPERTIES TIMEOUT 60)

add_executable(nex_task_debug_build_probe tests/task_debug_build.cpp)
target_link_libraries(nex_task_debug_build_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_task_debug_build_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
target_compile_options(nex_task_debug_build_probe PRIVATE -Wall -Wextra -Wpedantic)

add_executable(nex_task_debug_runtime_probe tests/task_debug_runtime.cpp
  runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp
  runtime/nex_task_frame.cpp runtime/nex_task_application.cpp runtime/nex_task_debug.cpp)
target_include_directories(nex_task_debug_runtime_probe PRIVATE runtime)
target_compile_definitions(nex_task_debug_runtime_probe PRIVATE
  NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_TASK_DEBUG_ENABLED)
target_link_libraries(nex_task_debug_runtime_probe PRIVATE Threads::Threads)
target_compile_options(nex_task_debug_runtime_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_debug_runtime_native COMMAND nex_task_debug_runtime_probe)
set_tests_properties(task_debug_runtime_native PROPERTIES TIMEOUT 120)

add_executable(nex_task_debug_registry_probe tests/task_debug_registry.cpp
  runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp
  runtime/nex_task_frame.cpp runtime/nex_task_application.cpp runtime/nex_task_debug.cpp)
target_include_directories(nex_task_debug_registry_probe PRIVATE runtime)
target_compile_definitions(nex_task_debug_registry_probe PRIVATE
  NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_TASK_DEBUG_ENABLED NEX_TASK_DEBUG_COMPLETION_ENABLED)
target_link_libraries(nex_task_debug_registry_probe PRIVATE Threads::Threads)
target_compile_options(nex_task_debug_registry_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_debug_registry_native COMMAND nex_task_debug_registry_probe)
set_tests_properties(task_debug_registry_native PROPERTIES TIMEOUT 120)

add_test(NAME task_debugging_native COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_debugging.py $<TARGET_FILE:nex>
  $<TARGET_FILE:nex_task_debug_build_probe>
  --versioned-probe $<TARGET_FILE:nex_task_debug_versioned_probe>)
set_tests_properties(task_debugging_native PROPERTIES TIMEOUT 900)

add_executable(nex_task_debug_ir_probe tests/task_debug_ir.cpp)
target_link_libraries(nex_task_debug_ir_probe PRIVATE nex_frontend)
target_compile_options(nex_task_debug_ir_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_debug_ir_native COMMAND nex_task_debug_ir_probe)
set_tests_properties(task_debug_ir_native PROPERTIES TIMEOUT 60)

add_executable(nex_task_debug_versioned_probe tests/task_debug_versioned.cpp)
target_link_libraries(nex_task_debug_versioned_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_task_debug_versioned_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
target_compile_options(nex_task_debug_versioned_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME task_debug_versioned_native COMMAND nex_task_debug_versioned_probe
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/language-0.19-sdk115-tasks.json
  ${CMAKE_CURRENT_BINARY_DIR}/task-debug-versioned-evidence)
set_tests_properties(task_debug_versioned_native PROPERTIES TIMEOUT 600)

add_test(NAME task_debug_native COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_debug_native.py
  $<TARGET_FILE:nex_task_debug_build_probe> $<TARGET_FILE:nex>)
set_tests_properties(task_debug_native PROPERTIES TIMEOUT 900)

# Resource-region/value transfer is part of TaskGroup. Standalone runtimes need
# the same host resource implementation, including when source transport is off.
get_directory_property(NEX_LOCAL_TARGETS BUILDSYSTEM_TARGETS)
foreach(NEX_LOCAL_TARGET IN LISTS NEX_LOCAL_TARGETS)
  get_target_property(NEX_LOCAL_DEFINITIONS ${NEX_LOCAL_TARGET} COMPILE_DEFINITIONS)
  get_target_property(NEX_LOCAL_SOURCES ${NEX_LOCAL_TARGET} SOURCES)
  if("NEX_ASYNC_TASKS" IN_LIST NEX_LOCAL_DEFINITIONS OR "runtime/nex_files.cpp" IN_LIST NEX_LOCAL_SOURCES)
    foreach(NEX_OWNED_RUNTIME runtime/nex_resource_region.cpp runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp)
      if(NOT NEX_OWNED_RUNTIME IN_LIST NEX_LOCAL_SOURCES)
        target_sources(${NEX_LOCAL_TARGET} PRIVATE ${NEX_OWNED_RUNTIME})
      endif()
    endforeach()
  endif()
endforeach()

# Private asynchronous TCP kernel. Public source network operations remain gated.
add_test(NAME dns_policy COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/dns_policy.py)
add_test(NAME dns_library COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/dns_library.py $<TARGET_FILE:nex>)
set_tests_properties(dns_policy PROPERTIES TIMEOUT 30)
set_tests_properties(dns_library PROPERTIES TIMEOUT 300)
set(NEX_CARES_PREFIX "" CACHE PATH "Explicit static PIC c-ares1.34.9 prefix for DNS operational conformance")
if(NEX_CARES_PREFIX AND (APPLE OR CMAKE_SYSTEM_NAME STREQUAL "Linux" OR WIN32))
  add_test(NAME task_dns_source COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/dns_provider/verify.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} --cares-prefix ${NEX_CARES_PREFIX})
  add_test(NAME task_dns_delivery COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/dns_provider/verify_delivery.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} --cares-prefix ${NEX_CARES_PREFIX} ${NEX_TEST_PACKAGE_NOTICES_ARGS})
  set_tests_properties(task_dns_source task_dns_delivery PROPERTIES TIMEOUT 900)
endif()
if(APPLE OR CMAKE_SYSTEM_NAME STREQUAL "Linux" OR WIN32)
  add_executable(nex_task_network_probe tests/task_network.cpp runtime/nex_task_network.cpp runtime/nex_task_external.cpp)
  target_include_directories(nex_task_network_probe PRIVATE runtime)
  target_compile_options(nex_task_network_probe PRIVATE -Wall -Wextra -Wpedantic)
  target_link_libraries(nex_task_network_probe PRIVATE Threads::Threads)
  add_test(NAME task_network_transport COMMAND nex_task_network_probe)
  set_tests_properties(task_network_transport PROPERTIES TIMEOUT 90)
  add_test(NAME task_tcp_source COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/tcp_provider/verify.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR})
  add_test(NAME task_tcp_delivery COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/tcp_provider/verify_delivery.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} ${NEX_TEST_PACKAGE_NOTICES_ARGS})
  set_tests_properties(task_tcp_source task_tcp_delivery PROPERTIES TIMEOUT 900)
endif()

# Ordinary HTTP client: portable validation always runs; real IO requires an
# explicitly selected, separately built static dependency cohort.
add_test(NAME http_client_policy COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/http_provider/check_inputs.py)
add_test(NAME http_client_library COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/http_client_library.py $<TARGET_FILE:nex>)
set_tests_properties(http_client_policy PROPERTIES TIMEOUT 30)
set_tests_properties(http_client_library PROPERTIES TIMEOUT 300)
add_test(NAME http_stream_library COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/http_stream_library.py $<TARGET_FILE:nex>)
set_tests_properties(http_stream_library PROPERTIES TIMEOUT 300)
set(NEX_HTTP_PREFIX "" CACHE PATH "Explicit static PIC curl/nghttp2/c-ares prefix for HTTP client conformance")
if(NEX_HTTP_PREFIX AND (APPLE OR CMAKE_SYSTEM_NAME STREQUAL "Linux" OR WIN32))
  add_test(NAME task_http_client_source COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/http_provider/verify.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} --http-prefix ${NEX_HTTP_PREFIX})
  add_test(NAME task_http_client_delivery COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/http_provider/verify_delivery.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} --http-prefix ${NEX_HTTP_PREFIX} ${NEX_TEST_PACKAGE_NOTICES_ARGS})
  set_tests_properties(task_http_client_source task_http_client_delivery PROPERTIES TIMEOUT 1200)
  foreach(transport http1 https1 https2)
    add_test(NAME http_stream_${transport}_functional COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/http_stream_provider/verify_functional.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} --http-prefix ${NEX_HTTP_PREFIX} --transport ${transport})
    set_tests_properties(http_stream_${transport}_functional PROPERTIES TIMEOUT 1200)
  endforeach()
  add_test(NAME http_stream_delivery_functional COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/http_stream_provider/verify_functional.py --compiler $<TARGET_FILE:nex> --resources ${CMAKE_CURRENT_SOURCE_DIR} --http-prefix ${NEX_HTTP_PREFIX} --transport https2 --case download-file --package ${NEX_TEST_PACKAGE_NOTICES_ARGS})
  set_tests_properties(http_stream_delivery_functional PROPERTIES TIMEOUT 1200)
endif()

# Private exception frontend/reference work; public source remains024.
add_executable(nex_source_exception_probe tests/source_exception_prototype.cpp src/typescript.cpp)
target_link_libraries(nex_source_exception_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_options(nex_source_exception_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME source_exception_prototype COMMAND nex_source_exception_probe)
set_tests_properties(source_exception_prototype PROPERTIES TIMEOUT 120)
add_test(NAME source_exception_discovery COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_discovery.py $<TARGET_FILE:nex>)
set_tests_properties(source_exception_discovery PROPERTIES TIMEOUT 120)

# Private native/reference source-exception agreement; no public build selection.
add_executable(nex_source_exception_native_probe tests/source_exception_native.cpp src/typescript.cpp)
target_link_libraries(nex_source_exception_native_probe PRIVATE nex_native_backend ${CMAKE_DL_LIBS})
set_target_properties(nex_source_exception_native_probe PROPERTIES ENABLE_EXPORTS ON)
add_test(NAME source_exception_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_native.py $<TARGET_FILE:nex_source_exception_native_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_exception_native PROPERTIES TIMEOUT 1200)

add_test(NAME source_exception_typescript COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_typescript.py $<TARGET_FILE:nex_source_exception_native_probe>)
set_tests_properties(source_exception_typescript PROPERTIES TIMEOUT 1200)

add_executable(nex_source_exception_tasks_probe tests/source_exception_tasks.cpp src/typescript.cpp)
target_link_libraries(nex_source_exception_tasks_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_options(nex_source_exception_tasks_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME source_exception_tasks_reference COMMAND nex_source_exception_tasks_probe)
set_tests_properties(source_exception_tasks_reference PROPERTIES TIMEOUT 120)

add_test(NAME source_exception_task_agreement COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_task_agreement.py $<TARGET_FILE:nex_source_exception_tasks_probe> $<TARGET_FILE:nex_source_exception_native_probe>)
set_tests_properties(source_exception_task_agreement PROPERTIES TIMEOUT 120)

add_test(NAME source_exception_tasks_typescript COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_tasks_typescript.py $<TARGET_FILE:nex_source_exception_tasks_probe>)
set_tests_properties(source_exception_tasks_typescript PROPERTIES TIMEOUT 1200)

add_executable(nex_source_exception_lifetime_probe tests/source_exception_lifetimes.cpp)
target_link_libraries(nex_source_exception_lifetime_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
target_compile_options(nex_source_exception_lifetime_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME source_exception_task_lifetimes COMMAND nex_source_exception_lifetime_probe)
set_tests_properties(source_exception_task_lifetimes PROPERTIES TIMEOUT 120)

add_test(NAME source_exception_lifetime_compatibility COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_lifetime_compatibility.py $<TARGET_FILE:nex_source_exception_lifetime_probe>)
set_tests_properties(source_exception_lifetime_compatibility PROPERTIES TIMEOUT 120)

add_test(NAME source_exception_task_ir_reference COMMAND nex_source_exception_tasks_probe --task-ir)
set_tests_properties(source_exception_task_ir_reference PROPERTIES TIMEOUT 120)
add_executable(nex_source_exception_task_ir_probe tests/source_exception_task_ir.cpp)
target_link_libraries(nex_source_exception_task_ir_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_source_exception_task_ir_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME source_exception_task_ir_machine COMMAND nex_source_exception_task_ir_probe)
add_test(NAME source_exception_task_ir_agreement COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_task_ir_agreement.py $<TARGET_FILE:nex_source_exception_tasks_probe>)
set_tests_properties(source_exception_task_ir_agreement PROPERTIES TIMEOUT 1200)
add_executable(nex_source_exception_task_native_emit_probe tests/source_exception_task_native.cpp)
target_link_libraries(nex_source_exception_task_native_emit_probe PRIVATE nex_native_backend)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  add_test(NAME native_fixture_image_identity COMMAND ${Python3_EXECUTABLE} -B
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/native_fixture_image_identity.py
    --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}
    --identity-probe $<TARGET_FILE:nex_source_exception_task_native_emit_probe>)
  set_tests_properties(native_fixture_image_identity PROPERTIES TIMEOUT 120)
endif()
add_test(NAME source_exception_host COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_host.py
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe>
  $<TARGET_FILE:nex_source_exception_tasks_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}
  --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY} --crypto-include ${OPENSSL_INCLUDE_DIR} --watch-compiler $<TARGET_FILE:nex>)
set_tests_properties(source_exception_host PROPERTIES TIMEOUT 2400)
add_test(NAME source_exception_task_native COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_task_native.py $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_exception_task_native PROPERTIES TIMEOUT 2400)
add_executable(nex_source_exception_task_scheduler_probe tests/source_exception_task_scheduler.cpp runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_resource_region.cpp runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp)
target_include_directories(nex_source_exception_task_scheduler_probe PRIVATE runtime)
target_compile_definitions(nex_source_exception_task_scheduler_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_PROFILE_ENABLED)
target_compile_options(nex_source_exception_task_scheduler_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_source_exception_task_scheduler_probe PRIVATE Threads::Threads)
add_test(NAME source_exception_task_scheduler COMMAND nex_source_exception_task_scheduler_probe)
set_tests_properties(source_exception_task_scheduler PROPERTIES TIMEOUT 120)
add_test(NAME source_exception_task_native_profile COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_task_profile.py $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_exception_task_native_profile PROPERTIES TIMEOUT 2400)
add_test(NAME source_exception_task_native_debug COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_task_debug.py $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_exception_task_native_debug PROPERTIES TIMEOUT 2400)
add_test(NAME source_exception_task_lldb COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_task_lldb.py $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_exception_task_lldb PROPERTIES TIMEOUT 2400)
add_test(NAME source_exception_task_watch COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_task_lldb.py $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --watch-compiler $<TARGET_FILE:nex>)
set_tests_properties(source_exception_task_watch PROPERTIES TIMEOUT 2400)

add_executable(nex_source_exception_http_request_probe tests/source_exception_http_request.cpp
  runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_frame.cpp runtime/nex_task_application.cpp
  runtime/nex_task_external.cpp runtime/nex_resource_region.cpp runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp)
target_include_directories(nex_source_exception_http_request_probe PRIVATE runtime)
target_compile_definitions(nex_source_exception_http_request_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(nex_source_exception_http_request_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_source_exception_http_request_probe PRIVATE Threads::Threads)
add_test(NAME source_exception_http_request_host COMMAND nex_source_exception_http_request_probe)
set_tests_properties(source_exception_http_request_host PROPERTIES TIMEOUT 120)
add_test(NAME source_exception_http COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_http.py
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --openssl-include ${OPENSSL_INCLUDE_DIR}
  --ssl-library ${NEX_PRIVATE_SSL_LIBRARY} --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY}
  --sqlite-library ${NEX_PRIVATE_SQLITE_LIBRARY})
set_tests_properties(source_exception_http PROPERTIES TIMEOUT 1800)

add_test(NAME source_exception_module_http COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_module_http.py
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --module-probe $<TARGET_FILE:nex_source_exception_modules_probe>
  --openssl-include ${OPENSSL_INCLUDE_DIR}
  --ssl-library ${NEX_PRIVATE_SSL_LIBRARY} --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY}
  --sqlite-library ${NEX_PRIVATE_SQLITE_LIBRARY}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-module-http-runtime)
set_tests_properties(source_exception_module_http PROPERTIES TIMEOUT 2400 RESOURCE_LOCK private_exception_http_runtime)

add_executable(nex_source_exception_modules_probe tests/source_exception_modules.cpp)
target_link_libraries(nex_source_exception_modules_probe PRIVATE nex_native_backend)

add_test(NAME source_exception_modules COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_modules.py
  $<TARGET_FILE:nex_source_exception_modules_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}
  --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY} --crypto-include ${OPENSSL_INCLUDE_DIR}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-modules-runtime)
set_tests_properties(source_exception_modules PROPERTIES TIMEOUT 2400 FIXTURES_SETUP private_exception_modules RESOURCE_LOCK private_exception_module_runtime)

add_test(NAME source_exception_frontiers COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_frontiers.py
  $<TARGET_FILE:nex_source_exception_modules_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}
  --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY} --crypto-include ${OPENSSL_INCLUDE_DIR}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-modules-runtime)
set_tests_properties(source_exception_frontiers PROPERTIES TIMEOUT 2400 FIXTURES_REQUIRED private_exception_modules RESOURCE_LOCK private_exception_module_runtime)

add_test(NAME source_exception_instances COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_instances.py
  $<TARGET_FILE:nex_source_exception_modules_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}
  --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY} --crypto-include ${OPENSSL_INCLUDE_DIR}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-modules-runtime)
set_tests_properties(source_exception_instances PROPERTIES TIMEOUT 2400 FIXTURES_REQUIRED private_exception_modules RESOURCE_LOCK private_exception_module_runtime)

add_test(NAME source_exception_module_profile COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_module_profile.py
  $<TARGET_FILE:nex_source_exception_modules_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}
  --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY} --crypto-include ${OPENSSL_INCLUDE_DIR}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-module-profile-runtime)
set_tests_properties(source_exception_module_profile PROPERTIES TIMEOUT 3000 RESOURCE_LOCK private_exception_module_profile_runtime)
add_test(NAME source_exception_module_http_profile COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_module_http_profile.py
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --module-probe $<TARGET_FILE:nex_source_exception_modules_probe>
  --openssl-include ${OPENSSL_INCLUDE_DIR}
  --ssl-library ${NEX_PRIVATE_SSL_LIBRARY} --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY}
  --sqlite-library ${NEX_PRIVATE_SQLITE_LIBRARY}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-module-http-profile-runtime)
set_tests_properties(source_exception_module_http_profile PROPERTIES TIMEOUT 3000 RESOURCE_LOCK private_exception_module_http_profile_runtime)

add_test(NAME source_exception_module_debug COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_module_debug.py
  $<TARGET_FILE:nex_source_exception_modules_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX}
  --debug-compiler $<TARGET_FILE:nex> --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY} --crypto-include ${OPENSSL_INCLUDE_DIR}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-module-debug-runtime)
set_tests_properties(source_exception_module_debug PROPERTIES TIMEOUT 3600 RESOURCE_LOCK private_exception_module_debug_runtime)

add_test(NAME source_exception_module_http_debug COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exception_module_http_debug.py
  $<TARGET_FILE:nex_source_exception_task_native_emit_probe> $<TARGET_FILE:nex_source_exception_tasks_probe>
  ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --module-probe $<TARGET_FILE:nex_source_exception_modules_probe>
  --debug-compiler $<TARGET_FILE:nex> --openssl-include ${OPENSSL_INCLUDE_DIR}
  --ssl-library ${NEX_PRIVATE_SSL_LIBRARY} --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY}
  --sqlite-library ${NEX_PRIVATE_SQLITE_LIBRARY}
  --runtime-cache ${CMAKE_CURRENT_BINARY_DIR}/source-exception-module-http-debug-runtime)
set_tests_properties(source_exception_module_http_debug PROPERTIES TIMEOUT 3600 RESOURCE_LOCK private_exception_module_http_debug_runtime)

add_executable(nex_store_transactions_probe tests/store_transactions.cpp runtime/nex_store.cpp)
target_include_directories(nex_store_transactions_probe PRIVATE runtime)
target_link_libraries(nex_store_transactions_probe PRIVATE SQLite::SQLite3 Threads::Threads)
target_compile_options(nex_store_transactions_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME store_transactions_native COMMAND nex_store_transactions_probe)
set_tests_properties(store_transactions_native PROPERTIES TIMEOUT 30)

add_test(NAME source_exceptions_public COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exceptions_public.py $<TARGET_FILE:nex>)
set_tests_properties(source_exceptions_public PROPERTIES TIMEOUT 1800)
add_test(NAME source_exception_handlers COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/exception_handlers.py $<TARGET_FILE:nex>)
set_tests_properties(source_exception_handlers PROPERTIES TIMEOUT 1800)
add_test(NAME source_finally_foundation COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/finally.py $<TARGET_FILE:nex>)
set_tests_properties(source_finally_foundation PROPERTIES TIMEOUT 600)
install(FILES tests/finally.py tests/support.py tests/package_notices.py DESTINATION share/nex/tests)
install(FILES tests/fixtures/language-0.26-finally-origin.json tests/fixtures/language-0.26-finally-origin.sql DESTINATION share/nex/tests/fixtures)
install(FILES tests/fixtures/language-0.25-handler-origin.json tests/fixtures/language-0.25-handler-origin.sql
  DESTINATION share/nex/tests/fixtures)
install(FILES tests/exception_handlers.py DESTINATION share/nex/tests)
add_test(NAME source_exceptions_migration COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exceptions_migration.py $<TARGET_FILE:nex>)
set_tests_properties(source_exceptions_migration PROPERTIES TIMEOUT 120)
add_test(NAME source_exceptions_http_public COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exceptions_http_public.py $<TARGET_FILE:nex>)
set_tests_properties(source_exceptions_http_public PROPERTIES TIMEOUT 1800)
add_executable(nex_source_exception_provider_records_probe tests/source_exception_provider_records.cpp)
target_link_libraries(nex_source_exception_provider_records_probe PRIVATE nex_native_backend nex_frontend Threads::Threads)
add_test(NAME source_exception_provider_records COMMAND nex_source_exception_provider_records_probe)
set_tests_properties(source_exception_provider_records PROPERTIES TIMEOUT 60)
add_test(NAME source_exceptions_projects COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exceptions_projects.py $<TARGET_FILE:nex>)
set_tests_properties(source_exceptions_projects PROPERTIES TIMEOUT 2400)
add_test(NAME source_exceptions_projects_debug COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_exceptions_projects.py $<TARGET_FILE:nex> --debug-only)
set_tests_properties(source_exceptions_projects_debug PROPERTIES TIMEOUT 1800)

# Install every indexed public025 source-error conformance resource.
install(FILES
  tests/source_exception_debug_host.h
  tests/source_exception_frontiers.py
  tests/source_exception_host.py
  tests/source_exception_http.py
  tests/source_exception_http_request.cpp
  tests/source_exception_instances.py
  tests/source_exception_lifetime_compatibility.py
  tests/source_exception_lifetimes.cpp
  tests/source_exception_modules.cpp
  tests/source_exception_modules.py
  tests/source_exception_native.cpp
  tests/source_exception_native.py
  tests/source_exception_prototype.cpp
  tests/source_exception_provider_records.cpp
  tests/source_exception_task_agreement.py
  tests/source_exception_task_debug.py
  tests/source_exception_task_ir.cpp
  tests/source_exception_task_ir_agreement.py
  tests/source_exception_task_lldb.py
  tests/source_exception_task_native.cpp
  tests/source_exception_task_native.py
  tests/source_exception_task_profile.py
  tests/source_exception_task_scheduler.cpp
  tests/source_exception_tasks.cpp
  tests/source_exception_tasks_typescript.py
  tests/source_exception_typescript.py
  tests/source_exceptions_http_public.py
  tests/source_exceptions_migration.py
  tests/source_exceptions_projects.py
  tests/source_exceptions_public.py
  DESTINATION share/nex/tests)
install(FILES
  tests/fixtures/source-exceptions/retained-024-graph.json
  tests/fixtures/source-exceptions/retained-024.json
  DESTINATION share/nex/tests/fixtures/source-exceptions)

add_test(NAME source_task_finally COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/task_finally.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_source_exception_tasks_probe>)
set_tests_properties(source_task_finally PROPERTIES TIMEOUT 1800)
install(FILES tests/task_finally.py DESTINATION share/nex/tests)

add_executable(nex_source_error_payload_probe tests/source_error_payload.cpp)
target_link_libraries(nex_source_error_payload_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_source_error_payload_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME source_error_owned_payload COMMAND nex_source_error_payload_probe)
set_tests_properties(source_error_owned_payload PROPERTIES TIMEOUT 60)

add_executable(nex_typed_source_probe tests/typed_source.cpp src/typescript.cpp)
target_link_libraries(nex_typed_source_probe PRIVATE nex_native_backend nex_frontend MLIR Threads::Threads)
target_compile_options(nex_typed_source_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME typed_source_frontend_reference COMMAND nex_typed_source_probe)
set_tests_properties(typed_source_frontend_reference PROPERTIES TIMEOUT 120)
install(FILES tests/typed_source.cpp DESTINATION share/nex/tests)

add_executable(nex_typed_source_typescript_probe tests/typed_source_typescript.cpp src/typescript.cpp)
target_link_libraries(nex_typed_source_typescript_probe PRIVATE nex_frontend Threads::Threads)
target_compile_options(nex_typed_source_typescript_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME typed_source_typescript COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_source_typescript.py $<TARGET_FILE:nex_typed_source_typescript_probe>)
set_tests_properties(typed_source_typescript PROPERTIES TIMEOUT 600)

add_executable(nex_typed_source_native_probe tests/typed_source_native.cpp)
target_link_libraries(nex_typed_source_native_probe PRIVATE nex_native_backend nex_frontend MLIR Threads::Threads)
target_compile_options(nex_typed_source_native_probe PRIVATE -Wall -Wextra -Wpedantic)
set_target_properties(nex_typed_source_native_probe PROPERTIES ENABLE_EXPORTS ON)
add_test(NAME typed_source_native COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_source_native.py $<TARGET_FILE:nex_typed_source_native_probe>
  --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(typed_source_native PROPERTIES TIMEOUT 1200)
install(FILES tests/typed_source_native.cpp tests/typed_source_native.py DESTINATION share/nex/tests)

install(FILES tests/typed_source_typescript.cpp tests/typed_source_typescript.py DESTINATION share/nex/tests)


install(FILES tests/source_error_native_packet.cpp DESTINATION share/nex/tests)

add_test(NAME typed_error_genuine026_origin COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_error_origin.py $<TARGET_FILE:nex> $<TARGET_FILE:nex_typed_error_migration_probe>)
set_tests_properties(typed_error_genuine026_origin PROPERTIES TIMEOUT 120)
install(FILES tests/typed_error_origin.py DESTINATION share/nex/tests)
install(FILES tests/fixtures/language-0.26-typed-origin.json tests/fixtures/language-0.26-typed-origin.sql
  DESTINATION share/nex/tests/fixtures)

add_executable(nex_typed_source_tasks_probe tests/typed_source_tasks.cpp src/typescript.cpp)
target_link_libraries(nex_typed_source_tasks_probe PRIVATE nex_native_backend nex_frontend MLIR Threads::Threads)
target_compile_options(nex_typed_source_tasks_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME typed_source_tasks COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_source_tasks.py $<TARGET_FILE:nex_typed_source_tasks_probe>
  --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --crypto-library ${NEX_PRIVATE_CRYPTO_LIBRARY} --crypto-include ${OPENSSL_INCLUDE_DIR})
set_tests_properties(typed_source_tasks PROPERTIES TIMEOUT 1800)
install(FILES tests/typed_source_tasks.cpp tests/typed_source_tasks.py DESTINATION share/nex/tests)

add_executable(nex_source_error_authority_kernel_probe tests/source_error_authority_kernel.cpp
  runtime/runtime.cpp runtime/nex_files.cpp runtime/nex_task_external.cpp
  runtime/nex_resource_region.cpp runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp)
target_include_directories(nex_source_error_authority_kernel_probe PRIVATE runtime)
target_compile_definitions(nex_source_error_authority_kernel_probe PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_PROFILE_ENABLED)
target_compile_options(nex_source_error_authority_kernel_probe PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(nex_source_error_authority_kernel_probe PRIVATE Threads::Threads)
add_test(NAME source_error_authority_kernel COMMAND nex_source_error_authority_kernel_probe)
set_tests_properties(source_error_authority_kernel PROPERTIES TIMEOUT 180)
install(FILES tests/source_error_authority_kernel.cpp DESTINATION share/nex/tests)
add_test(NAME source_error_authority_typescript COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_error_authority_typescript.py)
set_tests_properties(source_error_authority_typescript PROPERTIES TIMEOUT 180)
install(FILES tests/source_error_authority_typescript.py tests/source_error_authority_typescript.mjs DESTINATION share/nex/tests)
add_test(NAME typed_source_authority_provenance COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_source_authority.py $<TARGET_FILE:nex_typed_source_tasks_probe>)
set_tests_properties(typed_source_authority_provenance PROPERTIES TIMEOUT 180)
install(FILES tests/typed_source_authority.py DESTINATION share/nex/tests)
install(FILES tests/fixtures/typed-error-authority-static.json tests/fixtures/typed-error-authority-bounded.nex DESTINATION share/nex/tests/fixtures)

add_executable(nex_typed_error_migration_probe tests/typed_error_migration.cpp src/graph_migration.cpp
  src/project.cpp src/operation_store.cpp src/graph_store.cpp src/change_store.cpp src/typescript.cpp)
target_link_libraries(nex_typed_error_migration_probe PRIVATE nex_native_backend nex_frontend MLIR Threads::Threads)
target_compile_definitions(nex_typed_error_migration_probe PRIVATE NEX_VERSION="${PROJECT_VERSION}" NEX_BUILD_ID="${NEX_BUILD_ID}")
target_compile_options(nex_typed_error_migration_probe PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME typed_error_history_migration COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_error_migration.py $<TARGET_FILE:nex_typed_error_migration_probe>
  --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX} --ordinary-compiler $<TARGET_FILE:nex>)
set_tests_properties(typed_error_history_migration PROPERTIES TIMEOUT 900)
install(FILES tests/typed_error_migration.cpp tests/typed_error_migration.py DESTINATION share/nex/tests)
install(FILES tests/fixtures/language-0.26-modular-typed-origin.json tests/fixtures/language-0.26-modular-typed-origin.sql DESTINATION share/nex/tests/fixtures)

install(FILES tests/typed_task_protocol.cpp tests/typed_provider_records.cpp tests/typed_error_projects.py tests/typed_error_debugging.py tests/typed_web_delivery.py tests/typed_web_browser.py tests/workers-browser.spec.js DESTINATION share/nex/tests)
install(FILES tests/fixtures/web-026-sdk149-origin.json DESTINATION share/nex/tests/fixtures)

# Explicit027 graph recovery and pure scalar Wasm gates, before public selection.
add_executable(nex_typed_scalar_wasm_probe tests/typed_scalar_wasm.cpp src/wasm.cpp)
target_link_libraries(nex_typed_scalar_wasm_probe PRIVATE nex_native_backend nex_frontend)
target_compile_definitions(nex_typed_scalar_wasm_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME typed_scalar_wasm COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_scalar_wasm.py $<TARGET_FILE:nex_typed_scalar_wasm_probe>)
set_tests_properties(typed_scalar_wasm PROPERTIES TIMEOUT 600)
add_test(NAME typed_graph_snapshots COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_graph_snapshots.py $<TARGET_FILE:nex_typed_error_migration_probe> $<TARGET_FILE:nex>)
set_tests_properties(typed_graph_snapshots PROPERTIES TIMEOUT 900)
install(FILES tests/typed_graph_snapshots.py tests/typed_scalar_wasm.py tests/typed_scalar_wasm.cpp DESTINATION share/nex/tests)

# Keep the one-second admitted-FFI deadline test free of competing CTest builds.
set_tests_properties(public_task_resource_source PROPERTIES RUN_SERIAL TRUE)

install(FILES tests/source_exceptions_public.py DESTINATION share/nex/tests)

install(FILES tests/host_fixture.py tests/windows_loader_fixture.py tests/windows_workload_ownership.py tests/host_test.h tests/host_dlfcn.h tests/host_images.h tests/host_file_observers.h tests/native_tool_forwarder.cpp DESTINATION share/nex/tests)

# Explicit028 candidate; public source/default and immutable027 releases remain separate.
add_executable(nex_source_contracts_probe tests/source_contracts.cpp src/typescript.cpp)
target_link_libraries(nex_source_contracts_probe PRIVATE nex_native_backend nex_frontend MLIR Threads::Threads)
target_compile_options(nex_source_contracts_probe PRIVATE -Wall -Wextra -Wpedantic)
set_target_properties(nex_source_contracts_probe PROPERTIES ENABLE_EXPORTS ON)
add_test(NAME source_contracts COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_contracts.py $<TARGET_FILE:nex_source_contracts_probe>
  --native-host $<TARGET_FILE:nex_source_contract_host> --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_contracts PROPERTIES TIMEOUT 1200)
install(FILES tests/source_contracts.cpp tests/source_contracts.py DESTINATION share/nex/tests)
add_test(NAME source_contract_history_migration COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_contract_migration.py $<TARGET_FILE:nex_typed_error_migration_probe>
  $<TARGET_FILE:nex_source_contracts_probe> --native-host $<TARGET_FILE:nex_source_contract_host> --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_contract_history_migration PROPERTIES TIMEOUT 1200)
install(FILES tests/source_contract_migration.py DESTINATION share/nex/tests)
install(FILES tests/fixtures/language-0.27-contract-origin.json tests/fixtures/language-0.27-contract-origin.sql DESTINATION share/nex/tests/fixtures)
add_executable(nex_source_contract_host tests/source_contract_host.cpp runtime/runtime.cpp
  runtime/nex_files.cpp runtime/nex_task_external.cpp runtime/nex_task_frame.cpp runtime/nex_task_application.cpp
  runtime/nex_resource_region.cpp runtime/nex_external_resource.cpp runtime/nex_resource_executor.cpp)
target_compile_definitions(nex_source_contract_host PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_include_directories(nex_source_contract_host PRIVATE runtime tests)
target_link_libraries(nex_source_contract_host PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
set_target_properties(nex_source_contract_host PROPERTIES ENABLE_EXPORTS ON)
install(FILES tests/source_contract_host.cpp DESTINATION share/nex/tests)

add_test(NAME source_contract_projects COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_error_projects.py $<TARGET_FILE:nex_task_stream_project_probe>
  --compiler $<TARGET_FILE:nex> --source-language 0.28)
set_tests_properties(source_contract_projects PROPERTIES TIMEOUT 2400)

target_sources(nex_source_contracts_probe PRIVATE src/web.cpp src/task_process.cpp src/verification.cpp)
target_include_directories(nex_source_contracts_probe SYSTEM PRIVATE ${NEX_Z3_INCLUDE})
target_link_libraries(nex_source_contracts_probe PRIVATE ${NEX_Z3_LIBRARY})
target_compile_definitions(nex_source_contracts_probe PRIVATE ${NEX_NATIVE_DEFINITIONS})
add_test(NAME source_contract_cohorts COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_contract_cohorts.py $<TARGET_FILE:nex_task_stream_project_probe>
  $<TARGET_FILE:nex_source_contracts_probe>)
set_tests_properties(source_contract_cohorts PROPERTIES TIMEOUT 900)
install(FILES tests/source_contract_cohorts.py DESTINATION share/nex/tests)
add_test(NAME source_contract_debugging COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_error_debugging.py $<TARGET_FILE:nex_task_stream_project_probe>
  $<TARGET_FILE:nex> --source-language 0.28)
set_tests_properties(source_contract_debugging PROPERTIES TIMEOUT 1800 SKIP_RETURN_CODE 77)
add_test(NAME source_contract_web_delivery COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/typed_web_delivery.py $<TARGET_FILE:nex_task_stream_project_probe>
  $<TARGET_FILE:nex_typed_source_typescript_probe> $<TARGET_FILE:nex> --source-language 0.28)
set_tests_properties(source_contract_web_delivery PROPERTIES TIMEOUT 1800)

add_test(NAME source_contract_projection COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_contract_projection.py $<TARGET_FILE:nex_source_contracts_probe>
  --native-host $<TARGET_FILE:nex_source_contract_host> --compiler ${LLVM_TOOLS_BINARY_DIR}/clang++${CMAKE_EXECUTABLE_SUFFIX})
set_tests_properties(source_contract_projection PROPERTIES TIMEOUT 1200)
install(FILES tests/source_contract_projection.py DESTINATION share/nex/tests)

add_test(NAME source_contract_CLI COMMAND ${Python3_EXECUTABLE} -B
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/source_contract_cli.py $<TARGET_FILE:nex>)
set_tests_properties(source_contract_CLI PROPERTIES TIMEOUT 1800)
install(FILES tests/source_contract_cli.py DESTINATION share/nex/tests)

# Apply Windows defaults after all targets, including source-contract hosts,
# have been declared. Later hosts need the same NT imports, exports and stack.
# Standalone probes compile the same Windows file/ACL implementation as the
# frontend and must resolve its NT, crypto and security imports as well.
if(WIN32)
  get_directory_property(NEX_WINDOWS_TARGETS BUILDSYSTEM_TARGETS)
  foreach(NEX_WINDOWS_TARGET IN LISTS NEX_WINDOWS_TARGETS)
    get_target_property(NEX_WINDOWS_SOURCES ${NEX_WINDOWS_TARGET} SOURCES)
    if("runtime/nex_files.cpp" IN_LIST NEX_WINDOWS_SOURCES OR "${CMAKE_CURRENT_SOURCE_DIR}/runtime/nex_files.cpp" IN_LIST NEX_WINDOWS_SOURCES)
      target_link_libraries(${NEX_WINDOWS_TARGET} PRIVATE ntdll bcrypt advapi32)
    endif()
    if(NEX_WINDOWS_TARGET MATCHES "^nex_.*_probe$" OR NEX_WINDOWS_TARGET STREQUAL "typed_resource_ffi" OR NEX_WINDOWS_TARGET STREQUAL "external_values")
      target_link_libraries(${NEX_WINDOWS_TARGET} PRIVATE ws2_32)
    endif()
    if("runtime/third_party/tracy/public/TracyClient.cpp" IN_LIST NEX_WINDOWS_SOURCES)
      target_link_libraries(${NEX_WINDOWS_TARGET} PRIVATE secur32)
    endif()
    get_target_property(NEX_WINDOWS_TYPE ${NEX_WINDOWS_TARGET} TYPE)
    if(NEX_WINDOWS_TYPE STREQUAL "EXECUTABLE")
      # Match the ordinary Unix worker stack reservation so checked source
      # depth/action limits run before the Windows default1MiB is exhausted.
      target_link_options(${NEX_WINDOWS_TARGET} PRIVATE "-Wl,--stack,8388608")
      get_target_property(NEX_WINDOWS_EXPORTS ${NEX_WINDOWS_TARGET} ENABLE_EXPORTS)
      if(NEX_WINDOWS_EXPORTS)
        target_link_options(${NEX_WINDOWS_TARGET} PRIVATE "-Wl,--export-all-symbols")
      endif()
    endif()
    if(NEX_WINDOWS_TYPE STREQUAL "EXECUTABLE" AND NOT "${CMAKE_CURRENT_BINARY_DIR}/nex-host.rc" IN_LIST NEX_WINDOWS_SOURCES)
      target_sources(${NEX_WINDOWS_TARGET} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/nex-host.rc")
    endif()
  endforeach()
endif()
