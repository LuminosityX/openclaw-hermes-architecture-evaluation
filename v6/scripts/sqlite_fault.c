#define _GNU_SOURCE
#include <dlfcn.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <stdatomic.h>
#include <time.h>
static ssize_t (*rw)(int,const void*,size_t);
static ssize_t (*rp)(int,const void*,size_t,off_t);
static ssize_t (*rp64)(int,const void*,size_t,off64_t);
static int (*rf)(int);
static int (*rfd)(int);
static _Atomic unsigned events=0;
__attribute__((constructor)) static void init(void){rw=dlsym(RTLD_NEXT,"write");rp=dlsym(RTLD_NEXT,"pwrite");rp64=dlsym(RTLD_NEXT,"pwrite64");rf=dlsym(RTLD_NEXT,"fsync");rfd=dlsym(RTLD_NEXT,"fdatasync");}
static int fail(int fd,const char *operation){
 if(access("/fault-control/ENABLED",F_OK))return 0;
 char link[80],path[2048];snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);ssize_t n=readlink(link,path,sizeof(path)-1);if(n<0)return 0;path[n]=0;
 if(strncmp(path,"/state/",7)||(!strstr(path,".db")&&!strstr(path,".sqlite")))return 0;
 if(atomic_fetch_add(&events,1)<128){char line[2400];struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);int len=snprintf(line,sizeof(line),"{\"pid\":%d,\"operation\":\"%s\",\"path\":\"%s\",\"seconds\":%lld,\"nanoseconds\":%ld,\"errno\":%d}\n",getpid(),operation,path,(long long)t.tv_sec,t.tv_nsec,EIO);int out=syscall(SYS_openat,AT_FDCWD,"/fault-events/events.jsonl",O_WRONLY|O_APPEND|O_CREAT,0600);if(out>=0){syscall(SYS_write,out,line,len);syscall(SYS_close,out);}}
 errno=EIO;return 1;
}
ssize_t write(int fd,const void *b,size_t n){if(fail(fd,"write"))return -1;return rw(fd,b,n);}
ssize_t pwrite(int fd,const void *b,size_t n,off_t o){if(fail(fd,"pwrite"))return -1;return rp(fd,b,n,o);}
ssize_t pwrite64(int fd,const void *b,size_t n,off64_t o){if(fail(fd,"pwrite64"))return -1;return rp64(fd,b,n,o);}
int fsync(int fd){if(fail(fd,"fsync"))return -1;return rf(fd);}
int fdatasync(int fd){if(fail(fd,"fdatasync"))return -1;return rfd(fd);}
