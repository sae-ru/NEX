/* Freestanding scalar Wasm ABI 1. No host imports or application authority. */
#include <stdint.h>
typedef struct { const char *content,*source,*compiler; } NexFunction;
typedef struct { const NexFunction *function; const char *site,*kind; int64_t begin,end; } NexSite;
static volatile uint32_t remaining,depth,error_code;
static volatile int64_t error_line;
static const NexSite *volatile error_site;
enum { OVERFLOW=1,DIV_ZERO=2,ASSERTION=3,BUDGET=4,DEPTH=5,MATCH=6,FLOAT=7 };
__attribute__((noreturn)) static void fail(uint32_t code,int64_t line,const NexSite *site){
 if(!error_code){error_code=code;error_line=line;error_site=site;}
 __builtin_trap();
}
void nex_wasm_reset(uint32_t budget){remaining=budget;depth=0;error_code=0;error_line=0;error_site=0;}
uint32_t nex_wasm_error_code(void){return error_code;}
int64_t nex_wasm_error_line(void){return error_line;}
const char *nex_wasm_error_site(void){return error_site?error_site->site:0;}
void nex_wasm_enter_at(int64_t line,const NexSite *site){if(depth>=64)fail(DEPTH,line,site);++depth;}
void nex_wasm_leave(void){if(depth)--depth;}
void nex_poll_at(int64_t line,const NexSite *site){if(!remaining)fail(BUDGET,line,site);--remaining;}
int64_t nex_add_at(int64_t a,int64_t b,int64_t line,const NexSite *site){int64_t r;if(__builtin_add_overflow(a,b,&r))fail(OVERFLOW,line,site);return r;}
int64_t nex_sub_at(int64_t a,int64_t b,int64_t line,const NexSite *site){int64_t r;if(__builtin_sub_overflow(a,b,&r))fail(OVERFLOW,line,site);return r;}
int64_t nex_mul_at(int64_t a,int64_t b,int64_t line,const NexSite *site){int64_t r;if(__builtin_mul_overflow(a,b,&r))fail(OVERFLOW,line,site);return r;}
int64_t nex_neg_at(int64_t a,int64_t line,const NexSite *site){if(a==INT64_MIN)fail(OVERFLOW,line,site);return -a;}
int64_t nex_div_at(int64_t a,int64_t b,int64_t line,const NexSite *site){if(!b)fail(DIV_ZERO,line,site);if(a==INT64_MIN&&b==-1)fail(OVERFLOW,line,site);return a/b;}
int64_t nex_mod_at(int64_t a,int64_t b,int64_t line,const NexSite *site){if(!b)fail(DIV_ZERO,line,site);if(a==INT64_MIN&&b==-1)return 0;return a%b;}
static int nex_f64_finite(double value){union{double d;uint64_t u;}v;v.d=value;return ((v.u>>52)&0x7ff)!=0x7ff;}
double nex_f64_validate(double value,int64_t line,const NexSite *site){if(!nex_f64_finite(value))fail(FLOAT,line,site);return value;}
double nex_f64_add(double a,double b,int64_t line,const NexSite *site){double r=a+b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_sub(double a,double b,int64_t line,const NexSite *site){double r=a-b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_mul(double a,double b,int64_t line,const NexSite *site){double r=a*b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_div(double a,double b,int64_t line,const NexSite *site){double r=a/b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_neg(double a,int64_t line,const NexSite *site){double r=-a;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_as_f64(int64_t value,int64_t line,const NexSite *site){(void)line;(void)site;return (double)value;}
int64_t nex_f64_compare(double a,double b,int64_t operation,int64_t line,const NexSite *site){
 (void)line;(void)site;
 switch(operation){case 0:return a==b;case 1:return a!=b;case 2:return a<b;case 3:return a<=b;case 4:return a>b;case 5:return a>=b;default:return 0;}
}
double nex_f64_validate_at(double value,int64_t line,const NexSite *site){if(!nex_f64_finite(value))fail(FLOAT,line,site);return value;}
double nex_f64_add_at(double a,double b,int64_t line,const NexSite *site){double r=a+b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_sub_at(double a,double b,int64_t line,const NexSite *site){double r=a-b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_mul_at(double a,double b,int64_t line,const NexSite *site){double r=a*b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_div_at(double a,double b,int64_t line,const NexSite *site){double r=a/b;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
double nex_f64_neg_at(double a,int64_t line,const NexSite *site){double r=-a;if(!nex_f64_finite(r))fail(FLOAT,line,site);return r;}
int64_t nex_f64_compare_at(double a,double b,int64_t operation,int64_t line,const NexSite *site){
 (void)line;(void)site;
 switch(operation){case 0:return a==b;case 1:return a!=b;case 2:return a<b;case 3:return a<=b;case 4:return a>b;case 5:return a>=b;default:return 0;}
}
double nex_as_f64_at(int64_t value,int64_t line,const NexSite *site){(void)line;(void)site;return (double)value;}
void nex_assert_at(int64_t value,int64_t line,const NexSite *site){if(!value)fail(ASSERTION,line,site);}
void nex_match_fail_at(int64_t line,const NexSite *site){fail(MATCH,line,site);}
