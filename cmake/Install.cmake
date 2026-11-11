# Install layout and bundled resources.
#
# Included from the top-level CMakeLists after production targets are defined.

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
install(FILES tools/sdk_acceptance.py tools/sdk_host.py tools/sdk_stdlib.py tools/sdk_source_contracts.py tools/sdk_typed_source.py tools/sdk_task_limits.py tools/sdk_source_exceptions.py tools/sdk_source_handlers.py tools/server_workload.py tools/provider_sdk.py DESTINATION share/nex/tools)
install(FILES tools/compiler_cohort.py DESTINATION share/nex/tools)
install(FILES tools/ctest_report.py DESTINATION share/nex/tools)
install(DIRECTORY tools/llm/ DESTINATION share/nex/tools/llm PATTERN __pycache__ EXCLUDE)
install(FILES tests/task_http_server.py DESTINATION share/nex/tests)
install(DIRECTORY experiments/models/ DESTINATION share/nex/tools/models
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/owned-opencl/ DESTINATION share/nex/tools/owned-opencl
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/owned-metal/ DESTINATION share/nex/tools/owned-metal
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/owned-metal-codegen/ DESTINATION share/nex/tools/owned-metal-codegen
  PATTERN __pycache__ EXCLUDE)
install(DIRECTORY experiments/owned-cuda-codegen/ DESTINATION share/nex/tools/owned-cuda-codegen
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
install(FILES experiments/quality/llm_cost.py DESTINATION share/nex/experiments/quality)
install(DIRECTORY experiments/quality/llm-campaign-v1 DESTINATION share/nex/experiments/quality PATTERN __pycache__ EXCLUDE)
install(FILES tools/windows/job_observer.py DESTINATION share/nex/tools/windows)
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
