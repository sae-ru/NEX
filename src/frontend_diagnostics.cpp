#include "nex/frontend_diagnostics.h"
#include "llvm/Support/Base64.h"
#include <algorithm>

namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
constexpr size_t previewBytes=4096,labelBytes=1024;
bool utf8(const std::string &text){return llvm::json::isUTF8(text);}

bool continuation(unsigned char byte){return (byte&0xc0)==0x80;}
Object label(const std::string &text){
  bool valid=utf8(text);auto end=std::min(text.size(),labelBytes);
  if(valid)while(end<text.size()&&end&&continuation(static_cast<unsigned char>(text[end])))--end;
  auto selected=text.substr(0,end);
  return Object{{"encoding",valid?"utf-8":"base64"},{"data",valid?selected:llvm::encodeBase64(selected)},
    {"bytes",int64_t(text.size())},{"truncated",end!=text.size()},{"hash",hash(text)}};
}
std::string display(const std::string &text){
  if(utf8(text))return text;
  std::string result;const char *hex="0123456789abcdef";
  for(unsigned char byte:text){
    if(byte=='\\')result+="\\\\";
    else if((byte>=32&&byte<127)||byte=='\n'||byte=='\r'||byte=='\t')result+=char(byte);
    else{result+="\\x";result+=hex[byte>>4];result+=hex[byte&15];}
  }
  return result;
}
}
void attachFrontendDiagnostic(Error &error,const std::map<std::string,std::string> &sources,
    const std::string &entry,const std::string &kind,const std::string &phase,bool complete){
  Array files;int64_t bytes=0;
  for(const auto &[key,text]:sources){
    files.push_back(Object{{"key_base64",llvm::encodeBase64(key)},{"hash",hash(text)}});
    bytes+=int64_t(text.size());
  }
  Object ledger{{"schema","nex.frontend-inputs/1"},{"entry_base64",llvm::encodeBase64(entry)},
    {"input_kind",kind},{"complete",complete},{"files",std::move(files)}};
  auto key=error.span.file;auto selected=sources.find(key);
  if(selected==sources.end()&&kind!="project"&&key.empty()){
    selected=sources.find(entry);if(selected!=sources.end())key=selected->first;
  }
  JSON source=nullptr,location=nullptr,preview=nullptr;
  if(selected!=sources.end()){
    const auto &text=selected->second;bool valid=utf8(text);
    source=Object{{"key",label(key)},{"hash",hash(text)},{"bytes",int64_t(text.size())},{"utf8",valid}};
    bool located=error.span.begin<=error.span.end&&error.span.end<=text.size()&&
      ((!error.span.file.empty()&&error.span.file==key)||(error.span.file.empty()&&kind!="project"&&phase=="parse"));
    if(located)location=Object{{"kind","diagnostic_span"},{"byte_begin",int64_t(error.span.begin)},{"byte_end",int64_t(error.span.end)}};
    size_t begin=located&&error.span.begin>1024?error.span.begin-1024:0;
    size_t end=std::min(text.size(),begin+previewBytes);
    if(valid){
      while(begin<end&&continuation(static_cast<unsigned char>(text[begin])))++begin;
      while(end<text.size()&&end>begin&&continuation(static_cast<unsigned char>(text[end])))--end;
    }
    auto selectedText=text.substr(begin,end-begin);
    preview=Object{{"byte_begin",int64_t(begin)},{"byte_end",int64_t(end)},
      {"encoding",valid?"utf-8":"base64"},{"data",valid?selectedText:llvm::encodeBase64(selectedText)},
      {"truncated_before",begin!=0},{"truncated_after",end!=text.size()},
      {"focus_fully_visible",located&&error.span.begin>=begin&&error.span.end<=end}};
  }
  error.frontend=Object{{"schema","nex.frontend-diagnostic/1"},{"language",languageVersion},
    {"phase",phase},{"input_kind",kind},{"entry",label(entry)},
    {"source_inputs_hash",hash(json(std::move(ledger),false))},
    {"input_files",int64_t(sources.size())},{"input_bytes",bytes},{"source_inputs_complete",complete},
    {"reported_key",label(error.span.file)},{"source",std::move(source)},
    {"location",std::move(location)},{"preview",std::move(preview)}};
}
JSON diagnosticJSON(const Error &error,const std::string &toolchain,const std::string &build){
  Array escaped;
  auto safe=[&](const char *name,const std::string &value){if(!utf8(value))escaped.push_back(name);return display(value);};
  Object result{{"schema","nex.diagnostic/1"},{"ok",false},{"code",safe("code",error.code)},
    {"message",safe("message",error.what())},{"line",int64_t(error.span.line)},
    {"column",int64_t(error.span.column)},{"file",safe("file",error.span.file)},
    {"stdout",safe("stdout",error.output)}};
  if(!error.operationSite.empty()){
    result["operation_site"]=error.operationSite;result["revision"]=error.operationRevision;result["source_hash"]=error.operationSource;
  }
  if(!error.operationId.empty())result["operation_id"]=error.operationId;
  if(auto captured=error.frontend.getAsObject();captured&&captured->getString("phase")&&captured->getString("input_kind")&&captured->getString("source_inputs_hash")&&captured->get("location")){
    auto frontend=*captured;frontend["code_hash"]=hash(error.code);frontend["message_hash"]=hash(error.what());
    Object identity{{"schema","nex.frontend-diagnostic-id/1"},{"language",languageVersion},
      {"phase",*frontend.get("phase")},{"input_kind",*frontend.get("input_kind")},
      {"source_inputs_hash",*frontend.get("source_inputs_hash")},
      {"reported_key_hash",hash(error.span.file)},{"location",*frontend.get("location")},
      {"code_hash",hash(error.code)},{"message_hash",hash(error.what())}};
    if(auto watch=frontend.get("watch"))identity["watch"]=*watch;
    frontend["id"]=hash(json(std::move(identity),false));
    if(!toolchain.empty()&&!build.empty())frontend["compiler"]=Object{{"version",toolchain},{"build",build}};
    result["frontend"]=std::move(frontend);
  }
  if(!escaped.empty())result["escaped_fields"]=std::move(escaped);
  return result;
}
}
