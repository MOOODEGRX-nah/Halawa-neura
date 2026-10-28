/* One-click Linux launcher for a relocatable review bundle. No shell or installer. */
#define _POSIX_C_SOURCE 200809L
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char directory[PATH_MAX], target[PATH_MAX * 2], pythonpath[PATH_MAX * 4];
    ssize_t length = readlink("/proc/self/exe", directory, sizeof(directory) - 1);
    if (length < 0) { perror("launcher"); return 1; }
    directory[length] = '\0';
    char *slash = strrchr(directory, '/');
    if (!slash) return 1;
    *slash = '\0';
    if (snprintf(target, sizeof(target), "%s/opt/neura-ai/app/neura-desktop.py", directory) >= (int)sizeof(target)) return 1;
    if (snprintf(pythonpath, sizeof(pythonpath), "%s/opt/neura-ai/app:%s/opt/neura-ai/vendor", directory, directory) >= (int)sizeof(pythonpath)) return 1;
    if (setenv("PYTHONPATH", pythonpath, 1)) return 1;
    char **command = calloc((size_t)argc + 4, sizeof(char *));
    if (!command) return 1;
    command[0] = "/usr/bin/python";
    command[1] = target;
    command[2] = "--preview";
    for (int index = 1; index < argc; ++index) command[index + 2] = argv[index];
    execv(command[0], command);
    perror("Neura preview");
    free(command);
    return 1;
}
