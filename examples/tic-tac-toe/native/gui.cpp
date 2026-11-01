// Portable window/input/GPU adapter. NEX owns every game rule and score.
#define SDL_MAIN_HANDLED
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include "nex_ffi_module.h"
#include "signatures.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <wrl/client.h>
#endif

static void checked(bool ok) {if(!ok)throw std::runtime_error(SDL_GetError());}
struct HostStatus {nex_ffi_status value;};
static void host(nex_ffi_status status) {if(status!=NEX_FFI_OK)throw HostStatus{status};}
using Color=SDL_FColor;
static constexpr Color background{.047f,.071f,.110f,1},tile{.082f,.114f,.165f,1};
static constexpr Color cyan{.35f,.83f,1,1},orange{1,.63f,.42f,1},green{.61f,.96f,.71f,1};
static constexpr Color white{.92f,.95f,.98f,1},muted{.46f,.58f,.69f,1};

// Original 5x7 glyphs drawn as GPU rectangles: no system fonts or font runtime.
static std::array<uint8_t,5> glyph(uint32_t c) {
  if(c>='a'&&c<='z')c-=32;
  if(c>=0x430&&c<=0x44f)c-=32;
  switch(c) {
  case 'A':case 0x410:return {126,17,17,17,126};
  case 'B':case 0x412:return {127,73,73,73,54};
  case 'C':case 0x421:return {62,65,65,65,34};
  case 'D':return {127,65,65,34,28};
  case 'E':case 0x415:case 0x401:return {127,73,73,73,65};
  case 'F':return {127,9,9,9,1};
  case 'G':return {62,65,73,73,122};
  case 'H':case 0x41d:return {127,8,8,8,127};
  case 'I':return {65,65,127,65,65};
  case 'J':return {32,64,65,63,1};
  case 'K':case 0x41a:return {127,8,20,34,65};
  case 'L':return {127,64,64,64,64};
  case 'M':case 0x41c:return {127,2,12,2,127};
  case 'N':return {127,4,8,16,127};
  case 'O':case 0x41e:return {62,65,65,65,62};
  case 'P':case 0x420:return {127,9,9,9,6};
  case 'Q':return {62,65,81,33,94};
  case 'R':return {127,9,25,41,70};
  case 'S':return {38,73,73,73,50};
  case 'T':case 0x422:return {1,1,127,1,1};
  case 'U':return {63,64,64,64,63};
  case 'V':return {31,32,64,32,31};
  case 'W':return {63,64,48,64,63};
  case 'X':case 0x425:return {99,20,8,20,99};
  case 'Y':return {7,8,112,8,7};
  case 'Z':return {97,81,73,69,67};
  case 0x411:return {127,73,73,73,49}; // Б
  case 0x413:return {127,1,1,1,1};
  case 0x414:return {96,62,33,63,96};
  case 0x416:return {99,20,127,20,99};
  case 0x417:return {34,65,73,73,54};
  case 0x418:case 0x419:return {127,32,16,8,127};
  case 0x41b:return {64,62,1,1,127};
  case 0x41f:return {127,1,1,1,127};
  case 0x423:return {7,72,72,72,63};
  case 0x424:return {28,34,127,34,28};
  case 0x426:return {63,32,32,63,96};
  case 0x427:return {7,8,8,8,127};
  case 0x428:return {127,64,127,64,127};
  case 0x429:return {63,32,63,32,127};
  case 0x42a:return {1,127,72,72,48};
  case 0x42b:return {127,72,48,0,127};
  case 0x42c:return {127,72,72,72,48};
  case 0x42d:return {34,65,73,73,62};
  case 0x42e:return {127,8,62,65,62};
  case 0x42f:return {70,41,25,9,127};
  case '0':return {62,81,73,69,62};case '1':return {0,66,127,64,0};
  case '2':return {66,97,81,73,70};case '3':return {34,65,73,73,54};
  case '4':return {24,20,18,127,16};case '5':return {39,69,69,69,57};
  case '6':return {60,74,73,73,48};case '7':return {1,113,9,5,3};
  case '8':return {54,73,73,73,54};case '9':return {6,73,73,41,30};
  case '-':return {8,8,8,8,8};case '/':return {32,16,8,4,2};
  case ':':return {0,54,54,0,0};case '.':return {0,96,96,0,0};
  case '[':return {0,127,65,65,0};case ']':return {0,65,65,127,0};
  case '+':return {8,8,62,8,8};case ' ':return {};
  default:return {2,1,81,9,6};
  }
}
static uint32_t next(const std::string& text,size_t& at) {
  uint32_t c=uint8_t(text[at++]);if(c<128)return c;
  int count=c<224?1:c<240?2:3;c&=count==1?31:count==2?15:7;
  while(count--&&at<text.size())c=(c<<6)|(uint8_t(text[at++])&63);
  return c;
}

struct Window {
  SDL_Window* window=nullptr;SDL_Renderer* renderer=nullptr;
  SDL_ThreadID owner=SDL_GetCurrentThreadID();bool initialized=false,smoke=false;
  std::array<uint8_t,9> cells{};int turn=1,winner=0,line=-1,hover=-1,smokeStep=0;
  int64_t x=0,o=0,draws=0;std::string adapter;
  static constexpr float bx=24,by=130,side=528,cell=176;
  ~Window(){if(renderer)SDL_DestroyRenderer(renderer);if(window)SDL_DestroyWindow(window);if(initialized)SDL_QuitSubSystem(SDL_INIT_VIDEO);if(SDL_WasInit(0)==0)SDL_Quit();}
  void color(Color c){checked(SDL_SetRenderDrawColorFloat(renderer,c.r,c.g,c.b,c.a));}
  void rect(float x,float y,float w,float h,Color c){color(c);SDL_FRect r{x,y,w,h};checked(SDL_RenderFillRect(renderer,&r));}
  void text(float x,float y,float scale,const std::string& value,Color c) {
    std::vector<SDL_FRect> pixels;float origin=x;
    for(size_t i=0;i<value.size();) {uint32_t cp=next(value,i);if(cp=='\n'){x=origin;y+=10*scale;continue;}
      auto bits=glyph(cp);for(int col=0;col<5;++col)for(int row=0;row<7;++row)if(bits[col]&(1<<row))pixels.push_back({x+col*scale,y+row*scale,scale,scale});x+=6*scale;
    }
    color(c);if(!pixels.empty())checked(SDL_RenderFillRects(renderer,pixels.data(),int(pixels.size())));
  }
  void polygon(const std::vector<SDL_FPoint>& points,Color c) {
    std::vector<SDL_Vertex> vertices;std::vector<int> indices;
    for(auto p:points)vertices.push_back({p,c,{0,0}});
    for(size_t i=1;i+1<points.size();++i){indices.push_back(0);indices.push_back(int(i));indices.push_back(int(i+1));}
    checked(SDL_RenderGeometry(renderer,nullptr,vertices.data(),int(vertices.size()),indices.data(),int(indices.size())));
  }
  void rounded(float x,float y,float w,float h,float radius,Color c) {
    std::vector<SDL_FPoint> points;
    for(int k=0;k<4;++k){float cx=k==0||k==3?x+w-radius:x+radius,cy=k<2?y+h-radius:y+radius;
      for(int i=0;i<=8;++i){float a=(k*90+i*90.f/8)*3.14159265f/180;points.push_back({cx+radius*std::cos(a),cy+radius*std::sin(a)});}}
    polygon(points,c);
  }
  void stroke(float ax,float ay,float bx,float by,float width,Color c) {
    float length=std::hypot(bx-ax,by-ay),dx=-(by-ay)/length*width/2,dy=(bx-ax)/length*width/2;
    polygon({{ax+dx,ay+dy},{bx+dx,by+dy},{bx-dx,by-dy},{ax-dx,ay-dy}},c);
  }
  void ring(float x,float y,float radius,float width,Color c) {
    std::vector<SDL_Vertex> vertices;std::vector<int> indices;
    for(int i=0;i<=64;++i){float a=i*6.2831853f/64;for(float r:{radius-width/2,radius+width/2})vertices.push_back({{x+r*std::cos(a),y+r*std::sin(a)},c,{0,0}});}
    for(int i=0;i<64;++i){int a=i*2;for(int v:{a,a+1,a+2,a+1,a+3,a+2})indices.push_back(v);}
    checked(SDL_RenderGeometry(renderer,nullptr,vertices.data(),int(vertices.size()),indices.data(),int(indices.size())));
  }
  void render(bool present=true) {
    color(background);checked(SDL_RenderClear(renderer));
    text(28,27,2,"NEX / TIC-TAC-TOE",muted);text(24,64,4,"КРЕСТИКИ-НОЛИКИ",white);
    for(int i=0;i<9;++i){float x=bx+(i%3)*cell,y=by+(i/3)*cell;Color c=tile;
      if(i==hover&&!cells[i]&&!winner)c={.11f,.16f,.22f,1};rounded(x+4,y+4,cell-8,cell-8,12,c);
      float cx=x+cell/2,cy=y+cell/2;
      if(cells[i]==1){stroke(cx-34,cy-34,cx+34,cy+34,11,cyan);stroke(cx+34,cy-34,cx-34,cy+34,11,cyan);}
      if(cells[i]==2)ring(cx,cy,40,11,orange);
    }
    if(line>=0){float ax,ay,bxx,byy;
      if(line<3){ax=bx+cell/2;ay=by+(line+.5f)*cell;bxx=bx+2.5f*cell;byy=ay;}
      else if(line<6){ax=bx+(line-3+.5f)*cell;ay=by+cell/2;bxx=ax;byy=by+2.5f*cell;}
      else {ax=bx+(line==6?.5f:2.5f)*cell;ay=by+cell/2;bxx=bx+(line==6?2.5f:.5f)*cell;byy=by+2.5f*cell;}
      stroke(ax,ay,bxx,byy,6,green);
    }
    text(590,144,2,"ДВА ИГРОКА",muted);
    text(590,188,3,winner==3?"НИЧЬЯ":winner==1?"ПОБЕДИЛ X":winner==2?"ПОБЕДИЛ O":turn==1?"ХОД X":"ХОД O",winner?green:turn==1?cyan:orange);
    text(590,287,2,"СЧЁТ СЕССИИ",muted);text(590,324,4,"X "+std::to_string(x),cyan);text(746,324,4,"O "+std::to_string(o),orange);
    text(590,378,2,"НИЧЬИХ: "+std::to_string(draws),white);
    rounded(582,442,310,58,9,{.14f,.23f,.30f,1});text(600,463,2,"НОВАЯ ИГРА [R]",white);
    text(590,548,2,"КЛИК ПО КЛЕТКЕ\n\nESC - ВЫХОД",muted);
    text(28,704,1.5f,"GPU / "+adapter,green);
    if(present)checked(SDL_RenderPresent(renderer));
  }
  void create() {
    SDL_SetMainReady();checked(SDL_InitSubSystem(SDL_INIT_VIDEO));initialized=true;
    smoke=std::getenv("NEX_GAME_SMOKE")!=nullptr;
    window=SDL_CreateWindow("Крестики-нолики — NEX",930,740,SDL_WINDOW_RESIZABLE|SDL_WINDOW_HIGH_PIXEL_DENSITY|(smoke?SDL_WINDOW_HIDDEN:0));checked(window!=nullptr);
#ifdef _WIN32
    const char* backend="direct3d11";
#elif defined(__APPLE__)
    const char* backend="metal";
#else
    const char* backend="opengl";
#endif
    renderer=SDL_CreateRenderer(window,backend);checked(renderer!=nullptr);
    adapter=SDL_GetRendererName(renderer);if(adapter=="software")throw std::runtime_error("hardware GPU renderer required");
    checked(SDL_SetRenderLogicalPresentation(renderer,930,740,SDL_LOGICAL_PRESENTATION_LETTERBOX));checked(SDL_SetRenderVSync(renderer,1));
    checked(SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND));
#ifdef _WIN32
    using Microsoft::WRL::ComPtr;
    auto* device=static_cast<ID3D11Device*>(SDL_GetPointerProperty(SDL_GetRendererProperties(renderer),SDL_PROP_RENDERER_D3D11_DEVICE_POINTER,nullptr));
    if(!device)throw std::runtime_error("missing hardware D3D11 device");
    ComPtr<IDXGIDevice> dxgi;ComPtr<IDXGIAdapter> gpu;
    if(FAILED(device->QueryInterface(IID_PPV_ARGS(&dxgi)))||FAILED(dxgi->GetAdapter(&gpu)))throw std::runtime_error("cannot inspect GPU adapter");
    DXGI_ADAPTER_DESC desc{};if(FAILED(gpu->GetDesc(&desc)))throw std::runtime_error("cannot inspect GPU description");
    if(desc.VendorId==0x1414&&desc.DeviceId==0x8c)throw std::runtime_error("software WARP adapter is disabled");
    int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,desc.Description,-1,nullptr,0,nullptr,nullptr);if(size<=0)throw std::runtime_error("invalid adapter name");
    std::string name(size,'\0');WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,desc.Description,-1,name.data(),size,nullptr,nullptr);name.pop_back();adapter+=" / "+name;
#elif !defined(__APPLE__)
    render();using GetString=const unsigned char*(*)(unsigned);
    auto get=reinterpret_cast<GetString>(SDL_GL_GetProcAddress("glGetString"));auto name=get?get(0x1f01):nullptr;
    if(!name)throw std::runtime_error("cannot identify the OpenGL device");adapter+=" / "+std::string(reinterpret_cast<const char*>(name));
    std::string lower=adapter;std::transform(lower.begin(),lower.end(),lower.begin(),[](unsigned char c){return char(std::tolower(c));});
    for(auto word:{"llvmpipe","softpipe","software","swrast"})if(lower.find(word)!=std::string::npos)throw std::runtime_error("software OpenGL renderer is disabled");
#endif
    render();
  }
  int translate(SDL_Event event) {
    if(event.type==SDL_EVENT_QUIT||event.type==SDL_EVENT_WINDOW_CLOSE_REQUESTED)return -1;
    if(event.type==SDL_EVENT_KEY_DOWN){if(event.key.key==SDLK_ESCAPE)return -1;if(event.key.key==SDLK_R)return 10;}
    if(event.type==SDL_EVENT_WINDOW_EXPOSED||event.type==SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED){render();return 0;}
    if(event.type==SDL_EVENT_MOUSE_MOTION||event.type==SDL_EVENT_MOUSE_BUTTON_UP){
      checked(SDL_ConvertEventToRenderCoordinates(renderer,&event));float x=event.type==SDL_EVENT_MOUSE_MOTION?event.motion.x:event.button.x,y=event.type==SDL_EVENT_MOUSE_MOTION?event.motion.y:event.button.y;
      int cellIndex=x>=bx&&x<bx+side&&y>=by&&y<by+side?int((y-by)/cell)*3+int((x-bx)/cell):-1;
      if(event.type==SDL_EVENT_MOUSE_MOTION){if(hover!=cellIndex){hover=cellIndex;render();}return 0;}
      if(event.button.button!=SDL_BUTTON_LEFT)return 0;
      if(cellIndex>=0)return cellIndex+1;if(x>=582&&x<=892&&y>=442&&y<=500)return 10;
    }
    return 0;
  }
  int event(const nex_ffi_api_v1* api,nex_ffi_call call) {
    if(smoke){
      SDL_Event input{};
      if(smokeStep<5){static constexpr int cells[]={0,3,1,4,2};int index=cells[smokeStep++];
        input.type=SDL_EVENT_MOUSE_BUTTON_UP;input.button.windowID=SDL_GetWindowID(window);input.button.button=SDL_BUTTON_LEFT;
        checked(SDL_RenderCoordinatesToWindow(renderer,bx+(index%3+.5f)*cell,by+(index/3+.5f)*cell,&input.button.x,&input.button.y));
      }else{input.type=SDL_EVENT_KEY_DOWN;input.key.key=SDLK_ESCAPE;}
      checked(SDL_PushEvent(&input));
    }
    for(;;){SDL_Event input;if(SDL_WaitEventTimeout(&input,100)){int result=translate(input);if(result)return result;}host(api->poll(call));}
  }
  int64_t verify() {
    render(false);SDL_Surface* raw=SDL_RenderReadPixels(renderer,nullptr);checked(raw!=nullptr);
    SDL_Surface* pixels=SDL_ConvertSurface(raw,SDL_PIXELFORMAT_RGBA32);SDL_DestroySurface(raw);checked(pixels!=nullptr);
    int64_t accent=0;
    // Count actual colored marks only inside the board, excluding text/HUD.
    for(int y=int(by);y<int(by+side)&&y<pixels->h;++y)for(int x=int(bx);x<int(bx+side)&&x<pixels->w;++x){auto* p=static_cast<const uint8_t*>(pixels->pixels)+y*pixels->pitch+x*4;
      if((p[2]>150&&p[1]>150&&p[0]<180)||(p[0]>200&&p[1]>100&&p[2]<170)||(p[1]>200&&p[0]>100))++accent;}
    if(const char* capture=std::getenv("NEX_GAME_CAPTURE"))checked(SDL_SaveBMP(pixels,capture));
    SDL_DestroySurface(pixels);
    SDL_Event reset{};reset.type=SDL_EVENT_KEY_DOWN;reset.key.key=SDLK_R;
    if(translate(reset)!=10)throw std::runtime_error("reset key mapping failed");
    return accent;
  }
};

static void destroy(void* object){delete static_cast<Window*>(object);}
static nex_ffi_status factory(const nex_ffi_api_v1*,nex_ffi_call,void* user,void** out)noexcept {
  try{auto* w=new Window;*out=w;w->create();return NEX_FFI_OK;}
  catch(const std::exception& e){try{*static_cast<std::string*>(user)=e.what();}catch(...){}return NEX_FFI_INTERNAL;}
  catch(...){return NEX_FFI_INTERNAL;}
}
static nex_ffi_status invoke(const nex_ffi_api_v1* api,nex_ffi_call call,const nex_ffi_ref* args,uint64_t count,nex_ffi_ref* out,void* user)noexcept {
  int op=int(reinterpret_cast<uintptr_t>(user));
  if(api->struct_size<NEX_FFI_V1_RESOURCE_SIZE||count!=(op==1?0:op==3?8:1))return NEX_FFI_ARGUMENT;
  try{
    if(op==1){nex_ffi_type type=0;host(api->result_type(call,&type));host(api->type_child(call,type,0,0,&type));std::string error;nex_ffi_ref value=0;
      auto status=api->resource_create(call,type,sizeof(Window),factory,destroy,&error,&value);if(status){if(!error.empty())throw std::runtime_error(error);return status;}return api->make_success(call,value,out);}
    nex_ffi_type type=0;host(api->argument_type(call,0,&type));void* object=nullptr;host(api->resource_borrow(call,args[0],type,&object));auto& w=*static_cast<Window*>(object);
    if(SDL_GetCurrentThreadID()!=w.owner)return NEX_FFI_THREAD;
    if(op==2)return api->make_i64(call,w.event(api,call),out);
    if(op==3){uint64_t size=0,copied=0;host(api->byte_size(call,args[1],&size));if(size!=9)return NEX_FFI_ARGUMENT;host(api->copy_bytes(call,args[1],0,w.cells.data(),9,&copied));if(copied!=9)return NEX_FFI_BOUNDS;
      for(auto cell:w.cells)if(cell>2)return NEX_FFI_RANGE;
      int64_t v[6];for(int i=0;i<6;++i)host(api->get_i64(call,args[i+2],&v[i]));
      if(v[0]<1||v[0]>2||v[1]<0||v[1]>3||v[2]<-1||v[2]>7)return NEX_FFI_RANGE;
      w.turn=int(v[0]);w.winner=int(v[1]);w.line=int(v[2]);w.x=v[3];w.o=v[4];w.draws=v[5];w.render();return api->make_bool(call,1,out);}
    if(op==4)return api->make_string(call,reinterpret_cast<const uint8_t*>(w.adapter.data()),w.adapter.size(),out);
    return api->make_i64(call,w.verify(),out);
  }catch(const HostStatus& e){return e.value;}
  catch(const std::exception& e){std::fprintf(stderr,"GUI: %s\n",e.what());if(op==1){const char code[]="E_GUI_INIT";return api->make_failure(call,reinterpret_cast<const uint8_t*>(code),sizeof(code)-1,reinterpret_cast<const uint8_t*>(e.what()),std::strlen(e.what()),out);}return NEX_FFI_INTERNAL;}
  catch(...){return NEX_FFI_INTERNAL;}
}
static const nex_ffi_export_v1 exports[]={
  {sizeof(nex_ffi_export_v1),0,"open",PIN_OPEN,invoke,reinterpret_cast<void*>(1)},
  {sizeof(nex_ffi_export_v1),0,"event",PIN_EVENT,invoke,reinterpret_cast<void*>(2)},
  {sizeof(nex_ffi_export_v1),0,"draw",PIN_DRAW,invoke,reinterpret_cast<void*>(3)},
  {sizeof(nex_ffi_export_v1),0,"adapter",PIN_ADAPTER,invoke,reinterpret_cast<void*>(4)},
  {sizeof(nex_ffi_export_v1),0,"verify_gpu",PIN_VERIFY_GPU,invoke,reinterpret_cast<void*>(5)}
};
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1* nex_ffi_module_entry(uint32_t abi,uint32_t size){static const nex_ffi_module_v1 module{1,sizeof(nex_ffi_module_v1),std::size(exports),sizeof(nex_ffi_export_v1),exports};return abi==1&&size>=NEX_FFI_V1_RESOURCE_SIZE?&module:nullptr;}
