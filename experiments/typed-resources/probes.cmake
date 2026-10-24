get_filename_component(TYPED_NEX_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(TYPED_NEX_RUNTIME "${TYPED_NEX_SOURCE}/runtime")
set(TYPED_NEX_GENERATED "${CMAKE_CURRENT_BINARY_DIR}/typed-resource-fixtures")
execute_process(COMMAND "${Python3_EXECUTABLE}" -B "${TYPED_NEX_SOURCE}/tests/typed_resource_signatures.py" "${TYPED_NEX_GENERATED}" COMMAND_ERROR_IS_FATAL ANY)
foreach(target typed_resource_module_a typed_resource_module_b)
  add_library(${target} MODULE "${TYPED_NEX_SOURCE}/tests/typed_resource_module.c")
  target_include_directories(${target} PRIVATE "${TYPED_NEX_RUNTIME}" "${TYPED_NEX_GENERATED}")
  target_link_libraries(${target} PRIVATE Threads::Threads)
  set_target_properties(${target} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_VISIBILITY_PRESET hidden)
endforeach()
target_compile_definitions(typed_resource_module_b PRIVATE DIFFERENT_IMAGE=1)
add_executable(typed_resource_ffi "${TYPED_NEX_SOURCE}/tests/typed_resource_ffi.cpp"
  "${TYPED_NEX_RUNTIME}/nex_ffi.cpp" "${TYPED_NEX_RUNTIME}/nex_ffi_types.cpp"
  "${TYPED_NEX_RUNTIME}/nex_ffi_resources.cpp" "${TYPED_NEX_RUNTIME}/nex_external_resource.cpp"
  "${TYPED_NEX_RUNTIME}/nex_ffi_loader.cpp" "${TYPED_NEX_RUNTIME}/nex_foreign.cpp"
  "${TYPED_NEX_RUNTIME}/nex_files.cpp" "${TYPED_NEX_RUNTIME}/nex_json.cpp" "${TYPED_NEX_RUNTIME}/runtime.cpp")
target_include_directories(typed_resource_ffi PRIVATE "${TYPED_NEX_RUNTIME}")
target_compile_definitions(typed_resource_ffi PRIVATE NEX_PROFILE_ENABLED)
target_compile_options(typed_resource_ffi PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(typed_resource_ffi PRIVATE Threads::Threads OpenSSL::Crypto ${CMAKE_DL_LIBS})
add_dependencies(typed_resource_ffi typed_resource_module_a typed_resource_module_b)
add_test(NAME typed_external_resource_C_ABI COMMAND typed_resource_ffi $<TARGET_FILE:typed_resource_module_a> $<TARGET_FILE:typed_resource_module_b> "${TYPED_NEX_GENERATED}/signatures.json")
set_tests_properties(typed_external_resource_C_ABI PROPERTIES TIMEOUT 90)

# The main compiler regression also exercises the preceding owned-value layer.
if(NOT TARGET external_values)
  add_library(external_fixture MODULE "${TYPED_NEX_SOURCE}/tests/external_resource_module.c")
  add_executable(external_values "${TYPED_NEX_SOURCE}/tests/external_resource_values.cpp"
    "${TYPED_NEX_SOURCE}/tests/external_resource_old_forward.c"
    "${TYPED_NEX_RUNTIME}/nex_external_resource.cpp" "${TYPED_NEX_RUNTIME}/runtime.cpp"
    "${TYPED_NEX_RUNTIME}/nex_files.cpp" "${TYPED_NEX_RUNTIME}/nex_task_external.cpp"
    "${TYPED_NEX_RUNTIME}/nex_json.cpp" "${TYPED_NEX_RUNTIME}/nex_ffi.cpp"
    "${TYPED_NEX_RUNTIME}/nex_ffi_types.cpp" "${TYPED_NEX_RUNTIME}/nex_ffi_resources.cpp")
  target_include_directories(external_values PRIVATE "${TYPED_NEX_RUNTIME}")
  set_source_files_properties("${TYPED_NEX_SOURCE}/tests/external_resource_old_forward.c" PROPERTIES INCLUDE_DIRECTORIES "${TYPED_NEX_SOURCE}/tests/fixtures/ffi-0.37")
  target_compile_definitions(external_values PRIVATE NEX_PROFILE_ENABLED NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
  target_link_libraries(external_values PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
  add_dependencies(external_values external_fixture)
  add_test(NAME owned_external_values_native COMMAND external_values $<TARGET_FILE:external_fixture>)
  set_tests_properties(owned_external_values_native PROPERTIES TIMEOUT 90)
endif()
