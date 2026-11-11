#include "nex/formatting.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"
#include <algorithm>
#include <filesystem>

namespace nex {
namespace {
enum class Role { Plain, OpenType, CloseType, Prefix, OpenEffects, CloseEffects, Comment };
struct Item {
  std::string text;
  Role role=Role::Plain;
  unsigned newlines=0;
};
std::vector<Item> items(const std::string &source,const std::string &file){
  auto tokens=sourceTokens(source,file);
  auto hints=sourceFormatHints(source,file);
  std::vector<Item> result;size_t cursor=0;unsigned newlines=0;
  auto trivia=[&](size_t end){
    while(cursor<end){
      if(source[cursor]=='/'&&cursor+1<end&&source[cursor+1]=='/'){
        auto begin=cursor;while(cursor<end&&source[cursor]!='\n')++cursor;
        auto finish=cursor;
        if(finish>begin&&source[finish-1]=='\r'&&cursor<source.size()&&source[cursor]=='\n')--finish;
        result.push_back({source.substr(begin,finish-begin),Role::Comment,newlines});newlines=0;
      }else{if(source[cursor]=='\n')++newlines;++cursor;}
    }
  };
  for(const auto &token:tokens){
    trivia(token.span.begin);auto begin=token.span.begin;Role role=Role::Plain;
    if(hints.genericOpens.contains(begin))role=Role::OpenType;
    else if(hints.genericCloses.contains(begin))role=Role::CloseType;
    else if(hints.prefixes.contains(begin))role=Role::Prefix;
    else if(hints.effectBraces.contains(begin))role=token.text=="{"?Role::OpenEffects:Role::CloseEffects;
    if(role==Role::CloseType&&token.text==">="){
      result.push_back({">",role,newlines});result.push_back({"=",Role::Plain,0});
    }else result.push_back({token.text,role,newlines});
    cursor=token.span.end;newlines=0;
  }
  trivia(source.size());return result;
}
bool oneOf(const std::string &text,std::initializer_list<const char*> choices){
  return std::any_of(choices.begin(),choices.end(),[&](const char *choice){return text==choice;});
}
class Writer {
  std::string result;
public:
  unsigned indent=0;
  bool lineStart()const{return result.empty()||result.back()=='\n';}
  void newline(){if(!lineStart())result+='\n';}
  void blank(){newline();if(!result.empty()&&(result.size()<2||result[result.size()-2]!='\n'))result+='\n';}
  void emit(const std::string &text,bool space=false){
    if(lineStart())result.append(size_t(indent)*2,' ');
    else if(space)result+=' ';
    result+=text;
  }
  std::string finish(){
    while(!result.empty()&&result.back()=='\n')result.pop_back();
    result+='\n';return std::move(result);
  }
};
std::string render(const std::vector<Item> &input){
  Writer out;std::vector<std::string> groups;const Item *previous=nullptr;
  for(const auto &item:input){
    const auto &text=item.text;
    if(item.role==Role::Comment){
      if(item.newlines)out.newline();
      if(item.newlines>1)out.blank();
      out.emit(text,!out.lineStart());out.newline();previous=&item;continue;
    }
    const bool closeBlock=text=="}"&&item.role!=Role::CloseEffects;
    const bool closeGroup=closeBlock||text==")"||text=="]"||item.role==Role::CloseType||item.role==Role::CloseEffects;
    const bool openBlock=text=="{"&&item.role!=Role::OpenEffects;
    if(closeGroup){
      if(groups.empty())throw Error("E_INTERNAL","formatter grouping differs from parser");
      if(groups.back()!="effects")--out.indent;
      groups.pop_back();
    }
    if(previous){
      const auto &before=previous->text;
      const bool beforeBlock=before=="{"&&previous->role!=Role::OpenEffects;
      const bool afterBlock=before=="}"&&previous->role!=Role::CloseEffects;
      bool continuation=oneOf(text,{"else","catch","finally",",",";", ")", "]", "(", "[", ".", "::", "?", "+", "-", "*", "/", "%", "<", ">", "<=", ">=", "==", "!=", "&&", "||", "=>", "="});
      if((beforeBlock&&!closeBlock)||before==";"||
         (before==","&&!groups.empty()&&groups.back()=="block")||
         (afterBlock&&!continuation)|| (closeBlock&&!beforeBlock))out.newline();
      // Preserve intentional multiline argument/list/type layouts. Structural
      // blocks have their own fixed breaks; effects stay inline unless commented.
      if(item.newlines&&((closeGroup&&!closeBlock&&item.role!=Role::CloseEffects)||
         (!groups.empty()&&groups.back()!="block"&&groups.back()!="effects")))out.newline();
      if(item.newlines>1&&(before==";"||afterBlock||previous->role==Role::Comment))out.blank();
      bool space=true;
      if(oneOf(text,{",",";",":", ".", "::", ")", "]", "?"})||
         item.role==Role::OpenType||item.role==Role::CloseType||item.role==Role::OpenEffects||item.role==Role::CloseEffects)space=false;
      if(oneOf(before,{"(","[",".","::"})||previous->role==Role::OpenType||
         previous->role==Role::Prefix||previous->role==Role::OpenEffects)space=false;
      if(text=="(")space=oneOf(before,{"return","if","while","match"});
      if(text=="["&&!oneOf(before,{"return","if","while","match","=>","=",",","(","[","+","-","*","/","%","<",">","<=",">=","==","!=","&&","||"}))space=false;
      if(openBlock)space=true;
      if(closeBlock&&beforeBlock)space=false;
      if(text=="!"&&item.role!=Role::Prefix)space=true;
      out.emit(text,space);
    }else out.emit(text);
    if(openBlock||text=="("||text=="["||item.role==Role::OpenType||item.role==Role::OpenEffects){
      groups.push_back(openBlock?"block":item.role==Role::OpenEffects?"effects":text);
      if(item.role!=Role::OpenEffects)++out.indent;
    }
    previous=&item;
  }
  if(!groups.empty())throw Error("E_INTERNAL","formatter left unclosed parser groups");
  return out.finish();
}
}
std::string formatSource(const std::string &source,const std::string &file){
  if(source.size()>4*1024*1024)throw Error("E_LIMIT","format source exceeds 4 MiB");
  auto original=items(source,file);auto formatted=render(original);
  if(formatted.size()>4*1024*1024)throw Error("E_LIMIT","formatted source exceeds 4 MiB");
  auto checked=items(formatted,file);
  // Compare exact token spelling and ordered comments, after only the parser's
  // type-closing >= split. Never accept a lexical change introduced by spacing.
  if(original.size()!=checked.size())throw Error("E_INTERNAL","formatter changed source tokens");
  for(size_t i=0;i<original.size();++i)
    if(original[i].text!=checked[i].text||original[i].role!=checked[i].role)
      throw Error("E_INTERNAL","formatter changed source token spelling or role");
  if(render(checked)!=formatted)throw Error("E_INTERNAL","formatter result is not idempotent");
  return formatted;
}
void replaceFormattedSource(const std::string &file,const std::string &original,const std::string &formatted){
  namespace fs=std::filesystem;
  auto status=fs::symlink_status(file);
  if(!fs::is_regular_file(status))throw Error("E_FILE","fmt --write requires a regular non-symlink file");
  if(readFile(file)!=original)throw Error("E_CONFLICT","source changed during formatting");
  if(original==formatted)return;
  int fd=-1;llvm::SmallString<256> temporary;
  if(auto error=llvm::sys::fs::createUniqueFile(file+".fmt-%%%%%%",fd,temporary))throw Error("E_FILE","cannot create formatter temporary file: "+error.message());
  struct Cleanup{std::string file;~Cleanup(){std::error_code ignored;fs::remove(file,ignored);}} cleanup{temporary.str().str()};
  llvm::raw_fd_ostream output(fd,true);output<<formatted;output.close();
  if(output.has_error()){output.clear_error();throw Error("E_FILE","cannot write formatter temporary file");}
  fs::permissions(cleanup.file,status.permissions());
  if(fs::is_symlink(fs::symlink_status(file))||readFile(file)!=original)throw Error("E_CONFLICT","source changed before formatter replacement");
  if(auto error=llvm::sys::fs::rename(cleanup.file,file))throw Error("E_FILE","cannot replace formatted source: "+error.message());
}
llvm::json::Value sourceFormattingCapability(){
  return llvm::json::Object{{"command","nex fmt FILE [--check|--write] [--json]"},
    {"guide","docs/formatting.md"},{"schema","nex.format/1"},{"style","nex/1"},
    {"language",languageVersion},{"indent_spaces",2},{"line_endings","LF"},
    {"maximum_source_bytes",4*1024*1024},{"default_mode","preview"},
    {"comments_preserved",true},{"literal_spelling_preserved",true},{"parser_classified_tokens",true},
    {"idempotent",true},{"syntax_checked",true},{"type_checked",false},
    {"graph_store_opened",false},{"imports_loaded",false},{"language_migration",false},
    {"project_recursion",false},{"line_width_wrapping",false},
    {"exit_codes",llvm::json::Object{{"success",0},{"check_needs_formatting",1},{"invalid_input",1}}}};
}
}
