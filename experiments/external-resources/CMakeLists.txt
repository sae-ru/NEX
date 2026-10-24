cmake_minimum_required(VERSION 3.25)
project(NEXExternalResourceFoundation LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
find_package(Threads REQUIRED)
get_filename_component(NEX_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(NEX_RUNTIME "${NEX_SOURCE}/runtime")
add_library(external_fixture MODULE "${NEX_SOURCE}/tests/external_resource_module.c")
add_executable(external_values "${NEX_SOURCE}/tests/external_resource_values.cpp"
  "${NEX_SOURCE}/tests/external_resource_old_forward.c"
  "${NEX_RUNTIME}/nex_external_resource.cpp" "${NEX_RUNTIME}/nex_resource_region.cpp" "${NEX_RUNTIME}/nex_resource_executor.cpp" "${NEX_RUNTIME}/runtime.cpp"
  "${NEX_RUNTIME}/nex_files.cpp" "${NEX_RUNTIME}/nex_task_external.cpp"
  "${NEX_RUNTIME}/nex_json.cpp" "${NEX_RUNTIME}/nex_ffi.cpp" "${NEX_RUNTIME}/nex_ffi_types.cpp" "${NEX_RUNTIME}/nex_ffi_resources.cpp")
target_include_directories(external_values PRIVATE "${NEX_RUNTIME}")
set_source_files_properties("${NEX_SOURCE}/tests/external_resource_old_forward.c"
  PROPERTIES INCLUDE_DIRECTORIES "${NEX_SOURCE}/tests/fixtures/ffi-0.37")
target_compile_definitions(external_values PRIVATE NEX_PROFILE_ENABLED NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(external_values PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(external_values PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
enable_testing()
add_test(NAME owned_external_values COMMAND external_values $<TARGET_FILE:external_fixture>)
set_tests_properties(owned_external_values PROPERTIES TIMEOUT 60)

add_executable(legacy_file_values "${NEX_SOURCE}/tests/resource_values.cpp"
  "${NEX_RUNTIME}/runtime.cpp" "${NEX_RUNTIME}/nex_json.cpp"
  "${NEX_RUNTIME}/nex_files.cpp" "${NEX_RUNTIME}/files_runtime.cpp")
target_include_directories(legacy_file_values PRIVATE "${NEX_RUNTIME}")
target_compile_definitions(legacy_file_values PRIVATE NEX_PROFILE_ENABLED)
target_link_libraries(legacy_file_values PRIVATE Threads::Threads)
add_test(NAME existing_file_values COMMAND legacy_file_values)
set_tests_properties(existing_file_values PROPERTIES TIMEOUT 60)

add_executable(legacy_ffi "${NEX_RUNTIME}/nex_external_resource.cpp" "${NEX_RUNTIME}/nex_resource_region.cpp" "${NEX_RUNTIME}/nex_resource_executor.cpp" "${NEX_SOURCE}/tests/ffi_runtime.cpp" "${NEX_SOURCE}/tests/ffi_producer.c"
  "${NEX_RUNTIME}/nex_ffi.cpp" "${NEX_RUNTIME}/nex_ffi_types.cpp" "${NEX_RUNTIME}/nex_ffi_resources.cpp" "${NEX_RUNTIME}/nex_files.cpp" "${NEX_RUNTIME}/nex_json.cpp")
set_source_files_properties("${NEX_SOURCE}/tests/ffi_producer.c"
  PROPERTIES INCLUDE_DIRECTORIES "${NEX_SOURCE}/tests/fixtures/ffi-0.37")
target_include_directories(legacy_ffi PRIVATE "${NEX_RUNTIME}")
target_link_libraries(legacy_ffi PRIVATE Threads::Threads)
add_test(NAME existing_C_transport COMMAND legacy_ffi)
set_tests_properties(existing_C_transport PROPERTIES TIMEOUT 60)
