// Direct host control for the generated provider's actual context/cleanup code.
// A no-driver compile/control result is explicitly separate from CUDA success.
#include "module.cpp"
#ifndef NEX_CUDA_PROBE_INDEX
#define NEX_CUDA_PROBE_INDEX 0
#endif
static void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
static CUcontext current(Session &session){
  auto get=reinterpret_cast<decltype(&cuCtxGetCurrent)>(session.driver.symbol("cuCtxGetCurrent"));
  CUcontext context=nullptr;session.driver.check(get(&context),"cuCtxGetCurrent");return context;
}
int main(int argc,char **argv){
  const bool unavailable=argc==2&&std::string(argv[1])=="--expect-unavailable";
  const bool configuration=argc==2&&std::string(argv[1])=="--check-gate-config";
  try{
    require(argc==1||unavailable||configuration,"usage: context-probe [--expect-unavailable|--check-gate-config]");
    if(configuration){auto control=gateConfiguration();std::printf("{\"ok\":true,\"scope\":\"gate-config-host-control\",\"compiled\":%s,\"cycles\":%llu,\"repeats\":%u,\"actual_CUDA_contexts\":0}\n",GENERATED_ACCEPTANCE_GATE?"true":"false",static_cast<unsigned long long>(control.cycles),control.repeats);return 0;}
    unsigned polls=0;bool rejected=false,rolledBack=false;
    {
      Session caller;caller.start(NEX_CUDA_PROBE_INDEX);
      {
        Context callerFrame(caller);
        Session a,b;a.start(NEX_CUDA_PROBE_INDEX);
        require(current(caller)==caller.context,"session creation replaced its caller's CUDA context");
        b.start(NEX_CUDA_PROBE_INDEX);
        require(current(caller)==caller.context,"second session creation replaced its caller's CUDA context");
        nex_ffi_api_v1 api{};
        api.poll=[](nex_ffi_call token)->nex_ffi_status{++*reinterpret_cast<unsigned*>(uintptr_t(token));return NEX_FFI_OK;};
        {
          Context outer(a);auto buffer=std::make_unique<Buffer>();buffer->session=&a;buffer->bytes=4;
          a.driver.check(a.driver.p_cuMemAlloc(&buffer->pointer,4),"cuMemAlloc probe");ledger.allocate(4);
          {
            Context inner(b);
            try{Context forbidden(a,&api,nex_ffi_call(uintptr_t(&polls)));}
            catch(const Error &error){rejected=error.code=="E_DEVICE_REENTRANT";}
            require(rejected&&polls==0,"source reentry reached host polling or the active session");
            buffer.reset();require(ledger.bytes==0,"nested cleanup retained device memory");
            require(current(b)==b.context,"private buffer cleanup did not restore the inner CUDA context");
          }
          require(current(a)==a.context,"inner operation did not restore its parent context");
        }
        require(current(caller)==caller.context,"nested operations did not restore the caller context");
        api.poll=[](nex_ffi_call)->nex_ffi_status{return NEX_FFI_HOST_TRAP;};
        try{Context interrupted(a,&api,0);}catch(const HostStatus &error){rolledBack=error.value==NEX_FFI_HOST_TRAP;}
        require(rolledBack,"constructor host trap was lost");
        require(current(caller)==caller.context,"failed constructor changed the caller context");
        {Context restored(a);require(current(a)==a.context,"constructor failure retained TLS or the session mutex");}
        require(current(caller)==caller.context,"constructor retry did not restore the caller");
      }
      require(current(caller)==nullptr,"caller frame did not restore the initial empty context");
    }
    require(ledger.balanced(),"context probe left physical resources or cleanup errors");
    require(!unavailable,"CUDA was available during an explicitly unavailable-driver control");
    std::printf("{\"ok\":true,\"scope\":\"physical-CUDA-context-probe\",\"actual_CUDA_contexts\":3,\"actual_device_allocations\":1,\"caller_context_preserved\":true,\"source_reentry_rejected_before_poll\":true,\"nested_cleanup_restores_context\":true,\"constructor_trap_rolls_back\":true,\"physical_cleanup_verified\":true}\n");
    return 0;
  }catch(const Error &error){
    if(unavailable&&error.code=="E_COMPUTE_UNAVAILABLE"&&ledger.contexts==0&&ledger.buffers==0&&ledger.balanced()){
      std::printf("{\"ok\":true,\"scope\":\"unavailable-driver-host-control\",\"actual_CUDA_contexts\":0,\"actual_device_allocations\":0,\"error\":\"E_COMPUTE_UNAVAILABLE\",\"physical_CUDA_context_probe_passed\":false}\n");return 0;
    }
    std::fprintf(stderr,"CUDA context probe: %s: %s\n",error.code.c_str(),error.what());return 1;
  }catch(const std::exception &error){std::fprintf(stderr,"CUDA context probe: %s\n",error.what());return 1;}
}
