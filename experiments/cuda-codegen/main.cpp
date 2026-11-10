#include "emitter.h"
#include <filesystem>
#include <iostream>
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/SHA256.h"

int main(int argc,char **argv){
  try{
    if(argc!=5&&argc!=7&&argc!=9)throw nex::Error("E_OPTION","usage: nex-cuda-emit PROJECT SYMBOL rows|columns OUTPUT.cu [--list-capacity N] [--byte-capacity N]");
    unsigned capacity=32,byteCapacity=256;std::set<std::string> options;
    for(int i=5;i<argc;i+=2){
      const std::string option=argv[i];
      if((option!="--list-capacity"&&option!="--byte-capacity")||!options.insert(option).second)throw nex::Error("E_OPTION","invalid capacity option");
      const unsigned maximum=option=="--list-capacity"?1024:32760;unsigned value=0;
      for(char c:std::string(argv[i+1])){if(c<'0'||c>'9'||value>(maximum-unsigned(c-'0'))/10)throw nex::Error("E_OPTION","invalid CUDA capacity");value=value*10+unsigned(c-'0');}
      if(!value)throw nex::Error("E_OPTION","invalid CUDA capacity");
      (option=="--list-capacity"?capacity:byteCapacity)=value;
    }
    auto root=std::filesystem::canonical(argv[1]);
    auto manifest=llvm::json::parse(nex::readFile((root/"nex.json").string()));
    if(!manifest)throw nex::Error("E_MANIFEST",llvm::toString(manifest.takeError()));
    auto object=manifest->getAsObject();
    auto entry=object?object->getString("entry"):std::nullopt;
    if(!entry)throw nex::Error("E_MANIFEST","nex.json requires an entry");
    auto program=nex::loadProgram(entry->str(),root.string());
    auto emitted=nex::cuda_experiment::emitCuda(program,argv[2],argv[3],capacity,byteCapacity);
    llvm::json::Array parameters,functions;
    for(const auto &type:emitted.parameterTypes)parameters.push_back(type);
    for(const auto &f:emitted.functions)functions.push_back(llvm::json::Object{
      {"name",f.name},{"symbol",f.symbol},{"hash",f.hash},{"source",f.source.file},
      {"source_line",f.source.line},{"first_line",f.firstLine},{"last_line",f.lastLine}});
    // Validate and generate completely before touching the requested output.
    nex::writeFile(argv[4],emitted.source);
    auto shaderDigest=llvm::SHA256::hash(llvm::ArrayRef<uint8_t>(
      reinterpret_cast<const uint8_t*>(emitted.source.data()),emitted.source.size()));
    llvm::json::Object record{
      {"schema","nex.experimental-cuda-emission/1"},{"ok",true},{"experimental",true},
      {"integrated_compiler_CLI",false},{"driver_initialized",false},{"device_executed",false},
      {"frontend_archive_sha256",NEX_EXPERIMENT_FRONTEND_SHA256},
      {"language",nex::programLanguage(program)},{"revision",nex::revision(program)},
      {"entry",emitted.entry},{"input_layout",emitted.inputLayout},
      {"parameter_types",std::move(parameters)},{"result_type",emitted.resultType},
      {"kernel","nex_generated_cuda_map"},{"shader_sha256",llvm::toHex(shaderDigest,true)},
      {"source_bytes",uint64_t(emitted.source.size())},{"functions",std::move(functions)}};
    if(emitted.valueABI.getAsObject())record["value_abi"]=emitted.valueABI;
    if(emitted.floatingPoint)record["floating_point"]=llvm::json::Object{
      {"format","finite binary64"},{"word_encoding","IEEE754 bits"},{"rounding","nearest_ties_even"},
      {"positive_zero_normalized",true},{"nonfinite_status",7},{"host_environment_status",8},
      {"owned_provider_transport_accepted",false}};
    std::cout<<nex::json(std::move(record))<<'\n';
    return 0;
  }catch(const nex::Error &error){
    std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},
      {"message",error.what()},{"file",error.span.file},{"line",error.span.line}})<<'\n';return 1;
  }catch(const std::exception &error){
    std::cerr<<error.what()<<'\n';return 1;
  }
}
