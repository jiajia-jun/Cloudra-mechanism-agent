/* A native executable lets file managers run the portable app without shell prompts. */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char executable[PATH_MAX];
    ssize_t length = readlink("/proc/self/exe", executable, sizeof(executable) - 1);
    if (length < 0) {
        perror("Cloudra: cannot locate the application");
        return 1;
    }
    executable[length] = '\0';
    char *slash = strrchr(executable, '/');
    *slash = '\0';
    char script[PATH_MAX];
    if (snprintf(script, sizeof(script), "%s/launch-cloudra.sh", executable) >= (int)sizeof(script)) {
        fputs("Cloudra: installation path is too long\n", stderr);
        return 1;
    }
    char **arguments = calloc((size_t)argc + 2, sizeof(char *));
    if (arguments == NULL) {
        perror("Cloudra");
        return 1;
    }
    arguments[0] = "/bin/bash";
    arguments[1] = script;
    for (int index = 1; index < argc; index++) {
        arguments[index + 1] = argv[index];
    }
    execv(arguments[0], arguments);
    perror("Cloudra: cannot open the launcher");
    free(arguments);
    return 1;
}
