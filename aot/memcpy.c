#include <stdio.h>
#include <string.h>
#include <time.h>

static unsigned char source[1048576], destination[1048576];

static double seconds(void) {
    struct timespec time;
    clock_gettime(CLOCK_MONOTONIC, &time);
    return time.tv_sec + 1e-9 * time.tv_nsec;
}

int main(void) {
    for (unsigned i = 0; i < sizeof source; ++i)
        source[i] = (i * 13) ^ 55;
    for (int round = 0; round < 3; ++round) {
        double start = seconds();
        for (unsigned i = 0; i < 256; ++i) {
            source[i]++;
            memcpy(destination, source, sizeof source);
            source[(i + 17) % 256] = destination[255 - i];
        }
        printf("Copy sample %.6f s checksum=%u\n", seconds() - start, (unsigned)destination[0]);
        fflush(stdout);
    }
    puts("Copy benchmark complete");
    return 0;
}
