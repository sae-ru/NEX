#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
int main(void){
  static const unsigned char expected[32]={0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad};
  if(sizeof(void*)!=8||sizeof(long)!=4||sizeof(uint64_t)!=8)return 2;
  for(unsigned i=0;i<1000;++i){
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned char digest[EVP_MAX_MD_SIZE];unsigned size=0;
    if(!ctx)return 3;
    int ok=EVP_DigestInit_ex2(ctx,EVP_sha256(),NULL)==1&&EVP_DigestUpdate(ctx,"abc",3)==1&&EVP_DigestFinal_ex(ctx,digest,&size)==1;
    EVP_MD_CTX_free(ctx);if(!ok||size!=32||memcmp(digest,expected,32))return 4;
  }
  puts("Windows GNU/UCRT OpenSSL C ABI: 1000 SHA-256 checks passed");return 0;
}
