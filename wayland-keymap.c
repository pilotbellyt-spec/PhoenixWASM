// GEX's Wayland compositor sends an XKB map containing file includes.
// Give contexts parsing that map access to the packaged system XKB data.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdio.h>

// SQLite treats a failed main-database mapping as a request to use pread.
// Keep WAL's -shm mappings available, since SQLite uses them for coordination.
static int is_cache_database(int fd) {
    char link[64], path[4096];
    snprintf(link, sizeof link, "/proc/self/fd/%d", fd);
    ssize_t size = readlink(link, path, sizeof path - 1);
    if (size <= 0) return 0;
    path[size] = 0;
    const char *name = strrchr(path, '/');
    return name && strcmp(name, "/cache.sqlite") == 0;
}

void *mmap(void *addr, size_t length, int prot, int flags, int fd, off_t offset) {
    typedef void *(*map_fn)(void *, size_t, int, int, int, off_t);
    if (fd >= 0 && is_cache_database(fd)) {
        errno = ENODEV;
        return MAP_FAILED;
    }
    map_fn next = (map_fn)dlsym(RTLD_NEXT, "mmap");
    return next(addr, length, prot, flags, fd, offset);
}

void *mmap64(void *addr, size_t length, int prot, int flags, int fd, off64_t offset) {
    return mmap(addr, length, prot, flags, fd, (off_t)offset);
}

struct xkb_context;
struct xkb_context *xkb_context_new(int flags) {
    typedef struct xkb_context *(*create_context)(int);
    create_context create = (create_context)dlsym(RTLD_NEXT, "xkb_context_new");
    const int no_default_includes = 1;
    return create ? create(flags & ~no_default_includes) : 0;
}
