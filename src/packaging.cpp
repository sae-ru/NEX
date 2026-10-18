#include "nex/packaging.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/SHA256.h"
#include <cstdlib>
#include <filesystem>

namespace nex {
llvm::json::Value packageApplication(const Program &program, const BuildResult &built,
                                    const PackageOptions &options) {
  namespace fs=std::filesystem;
  auto output=fs::absolute(options.directory).lexically_normal();
  if(fs::exists(output)||fs::is_symlink(output))throw Error("E_EXISTS","package requires a new output directory");
  auto bytes=readFile(built.executable);
  auto digest=llvm::SHA256::hash(llvm::ArrayRef<uint8_t>(reinterpret_cast<const uint8_t*>(bytes.data()),bytes.size()));
  llvm::SmallString<128> temporary;
  if(auto error=llvm::sys::fs::createUniqueDirectory("nex-package",temporary))throw Error("E_FILE",error.message());
  auto folder=fs::path(temporary.str().str()),request=folder/"request.json";
  writeFile(request.string(),json(llvm::json::Object{{"schema","nex.application-request/1"},
    {"binary",built.executable},{"binary_sha256",llvm::toHex(digest,true)},
    {"runtime_notices",built.notices},{"sdk_root",fs::path(options.compiler).parent_path().parent_path().string()},
    {"toolchain",NEX_VERSION},{"language",languageVersion},{"revision",revision(program)},
    {"build_key",built.key},{"target",built.target},{"compiler_target",built.compilerTarget},
    {"host_compatible",built.hostCompatible}})+"\n");
  const char *python=std::getenv("NEX_PYTHON");
  std::vector<std::string> command={python?python:"python3",resourceFile("tools/app_bundle.py"),
    "--request",request.string(),"--output",output.string()};
  if(!options.notices.empty())command.insert(command.end(),{"--notices",fs::absolute(options.notices).string()});
  if(options.dpkgNotices)command.push_back("--dpkg-notices");
  auto result=capture(command,300);
  if(result.code!=0)throw Error("E_PACKAGE","application packaging failed; request retained at "+request.string()+"\n"+result.errors);
  auto parsed=llvm::json::parse(result.output);
  if(!parsed){llvm::consumeError(parsed.takeError());throw Error("E_PACKAGE","invalid package report; request retained at "+request.string());}
  auto object=parsed->getAsObject();
  if(!object||object->getString("schema")!="nex.package/1"||object->getBoolean("ok")!=true||object->getString("build_key")!=built.key)
    throw Error("E_PACKAGE","package report does not match the selected native build");
  fs::remove_all(folder);return std::move(*parsed);
}
}
