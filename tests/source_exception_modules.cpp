#include "nex/private_task_modules.h"
#include "nex/task_frontend.h"
#include "nex/operations.h"
#include <filesystem>
#include <iostream>
#include <charconv>
using namespace nex;
llvm::json::Object objectFile(const std::string &file){auto value=llvm::json::parse(readFile(file));if(!value){llvm::consumeError(value.takeError());throw std::runtime_error("expected JSON");}if(!value->getAsObject())throw std::runtime_error("expected JSON object");return llvm::json::Object(*value->getAsObject());}
int main(int argc,char **argv){try{
 if(argc>=3&&argc<=6&&std::string(argv[1])=="instances"){
  auto number=[](const char *text){std::string value=text;unsigned n=0;auto result=std::from_chars(value.data(),value.data()+value.size(),n);if(result.ec!=std::errc{}||result.ptr!=value.data()+value.size())throw std::runtime_error("expected unsigned catalogue offset/limit");return n;};
  auto p=loadSourceExceptionTaskContext(objectFile(argv[2]));std::cout<<json(describeSourceExceptionTaskInstances(p,argc>=4?argv[3]:"",argc>=5?number(argv[4]):0,argc>=6?number(argv[5]):64))<<'\n';return 0;
 }
 if(argc<4)throw std::runtime_error("expected instances private-context or plan|emit|validate private-context architecture ...");
 auto p=loadSourceExceptionTaskContext(objectFile(argv[2]));auto architecture=objectFile(argv[3]);
 if(argc==4&&std::string(argv[1])=="debug-context"){std::cout<<json(sourceExceptionTaskModuleDebugContext(p,architecture))<<'\n';return 0;}
 if(argc==4&&std::string(argv[1])=="plan"){std::cout<<json(planSourceExceptionTaskModules(p,architecture))<<'\n';return 0;}
 if(argc==6&&std::string(argv[1])=="validate"){validateSourceExceptionTaskModule(p,architecture,argv[4],objectFile(argv[5]));std::cout<<"{\"ok\":true}\n";return 0;}
 if(argc!=9||std::string(argv[1])!="emit")throw std::runtime_error("expected emit context architecture component output triple layout optimized");
 auto result=emitSourceExceptionTaskModule(p,architecture,argv[4],std::string(argv[8])=="true");auto out=std::filesystem::absolute(argv[5]);std::filesystem::create_directories(out);
 writeFile((out/"module-record.json").string(),json(std::move(result.record))+"\n");writeFile((out/"module.mlir").string(),result.native.mlir);writeFile((out/"module.ll").string(),lowerMLIRToLLVM(result.native.mlir,p.path,argv[6],argv[7]));
 llvm::json::Array operations;for(const auto &f:p.functions)for(const auto &o:operationTree(p,f))operations.push_back(llvm::json::Object{{"site",o.site},{"kind",o.kind},{"begin",int64_t(o.span.begin)-int64_t(f.span.begin)},{"end",int64_t(o.span.end)-int64_t(f.span.begin)},{"function_hash",hash(json(canonical(f),false))},{"function_source_hash",hash(p.definition(f))},{"line",int64_t(o.span.line)},{"column",int64_t(o.span.column)}});
 writeFile((out/"metadata.json").string(),json(llvm::json::Object{{"descriptor_symbol",result.native.descriptorSymbol},{"descriptor_abi",result.native.descriptorABI},{"operations",std::move(operations)}})+"\n");return 0;
}catch(const Error &e){std::cerr<<e.code<<": "<<e.what()<<" at "<<e.span.file<<":"<<e.span.line<<'\n';}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';}return 1;}
