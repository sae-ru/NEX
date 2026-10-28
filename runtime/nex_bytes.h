#pragma once
#include "nex_error.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace nexrt {
// Internal binary-value primitive. Host imports/exports copy; slices retain
// immutable storage. A view borrows from this value and cannot outlive it.
class ByteBuffer {
  friend struct ByteData;
  friend class TextFiles;
  friend class FileResource;
  using Storage = std::vector<uint8_t>;
  std::shared_ptr<const Storage> storage;
  size_t offset=0, count=0;
  ByteBuffer(std::shared_ptr<const Storage> storage,size_t offset,size_t count)
      :storage(std::move(storage)),offset(offset),count(count){}
  static void sizeAllowed(size_t size){
    if(size>uint64_t(std::numeric_limits<int64_t>::max())||size>Storage().max_size())
      throw DataError("E_LIMIT","byte buffer exceeds supported size");
  }
  static ByteBuffer owned(Storage value){
    if(value.empty())return {};
    auto size=value.size();sizeAllowed(size);
    return ByteBuffer(std::make_shared<const Storage>(std::move(value)),0,size);
  }
  static uint8_t byte(int64_t value){
    if(value<0||value>255)throw DataError("E_RANGE","byte value must be between 0 and 255");
    return uint8_t(value);
  }
  size_t index(int64_t value) const {
    if(value<0||uint64_t(value)>=count)throw DataError("E_BOUNDS","byte index is outside buffer bounds");
    return size_t(value);
  }
public:
  ByteBuffer()=default;
  ByteBuffer(const ByteBuffer&)=default;
  ByteBuffer &operator=(const ByteBuffer&)=default;
  ByteBuffer(ByteBuffer &&other) noexcept
      :storage(std::move(other.storage)),offset(other.offset),count(other.count){other.offset=other.count=0;}
  ByteBuffer &operator=(ByteBuffer &&other) noexcept {
    if(this!=&other){storage=std::move(other.storage);offset=other.offset;count=other.count;other.offset=other.count=0;}
    return *this;
  }
  static ByteBuffer copy(std::span<const uint8_t> values){
    sizeAllowed(values.size());if(values.empty())return {};
    return owned(Storage(values.begin(),values.end()));
  }
  static ByteBuffer fromIntegers(std::span<const int64_t> values){
    sizeAllowed(values.size());Storage result;result.reserve(values.size());
    for(auto value:values)result.push_back(byte(value));
    return owned(std::move(result));
  }
  int64_t length() const {return int64_t(count);}
  std::span<const uint8_t> view() const {
    if(!count)return {};
    return {storage->data()+offset,count};
  }
  Storage toVector() const {
    if(!count)return {};
    auto bytes=view();return {bytes.begin(),bytes.end()};
  }
  int64_t at(int64_t position) const {auto selected=index(position);return (*storage)[offset+selected];}
  ByteBuffer slice(int64_t start,int64_t length) const {
    if(start<0||length<0||uint64_t(start)>count||uint64_t(length)>count-uint64_t(start))
      throw DataError("E_BOUNDS","slice is outside byte buffer bounds");
    if(!length)return {};
    return ByteBuffer(storage,offset+size_t(start),size_t(length));
  }
  ByteBuffer set(int64_t position,int64_t value) const {
    auto selected=index(position);auto replacement=byte(value);
    if((*storage)[offset+selected]==replacement)return *this;
    auto result=toVector();result[selected]=replacement;return owned(std::move(result));
  }
  ByteBuffer append(int64_t value) const {
    auto replacement=byte(value);
    if(count==size_t(std::numeric_limits<int64_t>::max()))throw DataError("E_LIMIT","byte buffer exceeds supported size");
    sizeAllowed(count+1);auto result=toVector();result.push_back(replacement);return owned(std::move(result));
  }
  ByteBuffer concat(const ByteBuffer &other) const {
    if(other.count>uint64_t(std::numeric_limits<int64_t>::max())-count)
      throw DataError("E_LIMIT","byte buffer exceeds supported size");
    auto total=count+other.count;sizeAllowed(total);
    if(!count)return other;if(!other.count)return *this;
    Storage result;result.reserve(total);auto a=view(),b=other.view();
    result.insert(result.end(),a.begin(),a.end());result.insert(result.end(),b.begin(),b.end());
    return owned(std::move(result));
  }
  bool operator==(const ByteBuffer &other) const {
    if(count!=other.count)return false;
    if(!count||(storage==other.storage&&offset==other.offset))return true;
    auto a=view(),b=other.view();return std::equal(a.begin(),a.end(),b.begin());
  }
  std::string base64() const {
    static constexpr char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    auto groups=count/3+size_t(count%3!=0);std::string result;
    if(groups>result.max_size()/4)throw DataError("E_LIMIT","encoded bytes exceed supported size");
    result.reserve(groups*4);auto data=view();
    for(size_t i=0;i<count;i+=3){
      auto a=data[i];auto b=i+1<count?data[i+1]:uint8_t(0);auto c=i+2<count?data[i+2]:uint8_t(0);
      result+=alphabet[a>>2];result+=alphabet[((a&3)<<4)|(b>>4)];
      result+=i+1<count?alphabet[((b&15)<<2)|(c>>6)]:'=';result+=i+2<count?alphabet[c&63]:'=';
    }
    return result;
  }
  static ByteBuffer fromBase64(std::string_view text){
    static constexpr auto table=[](){
      std::array<int8_t,256> result{};result.fill(-1);
      constexpr std::string_view alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
      for(size_t i=0;i<alphabet.size();++i)result[uint8_t(alphabet[i])]=int8_t(i);
      return result;
    }();
    auto invalid=[]()->void{throw DataError("E_BASE64","invalid canonical base64");};
    if(text.size()%4)invalid();if(text.empty())return {};
    auto padding=size_t(text.back()=='=')+size_t(text[text.size()-2]=='=');
    auto expected=text.size()/4*3-padding;sizeAllowed(expected);Storage result;result.reserve(expected);
    for(size_t i=0;i<text.size();i+=4){
      auto a=table[uint8_t(text[i])],b=table[uint8_t(text[i+1])];
      if(a<0||b<0)invalid();
      auto c=text[i+2],d=text[i+3];bool last=i+4==text.size();
      if(c=='='){
        if(!last||d!='='||(b&15))invalid();result.push_back(uint8_t((a<<2)|(b>>4)));continue;
      }
      auto cv=table[uint8_t(c)];if(cv<0)invalid();
      result.push_back(uint8_t((a<<2)|(b>>4)));
      if(d=='='){
        if(!last||(cv&3))invalid();result.push_back(uint8_t((b<<4)|(cv>>2)));continue;
      }
      auto dv=table[uint8_t(d)];if(dv<0)invalid();
      result.push_back(uint8_t((b<<4)|(cv>>2)));result.push_back(uint8_t((cv<<6)|dv));
    }
    return owned(std::move(result));
  }
};
}
