#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>
#include <regex.h>
#include <yaml.h>
#include <stdbool.h>
#include <ctype.h>
#include <time.h>

#define MAX_PATH_LEN 4096
#define MAX_LINE_LEN 1024
#define MAX_PATTERN_NAME 256
#define MAX_RULES_PER_FILE 1000
#define DEFAULT_RULES_DIR "/opt/regex/list"

typedef struct {
    char name[MAX_PATTERN_NAME];
    regex_t regex;
    bool compiled;
} PatternRule;

typedef struct {
    PatternRule *rules;
    int count;
    char filename[MAX_PATH_LEN];
} RuleFile;

typedef struct {
    RuleFile *files;
    int file_count;
    int total_rules;
} RuleCollection;

// ANSI color codes for better output
#define COLOR_RED     "\x1b[31m"
#define COLOR_GREEN   "\x1b[32m"
#define COLOR_YELLOW  "\x1b[33m"
#define COLOR_BLUE    "\x1b[34m"
#define COLOR_MAGENTA "\x1b[35m"
#define COLOR_CYAN    "\x1b[36m"
#define COLOR_RESET   "\x1b[0m"
#define COLOR_BOLD    "\x1b[1m"

// Function prototypes
void init_rule_collection(RuleCollection *rc);
void free_rule_collection(RuleCollection *rc);
bool load_rules_from_file(RuleCollection *rc, const char *filename);
void load_all_rule_files(RuleCollection *rc, const char *dir_path);
void scan_token(const RuleCollection *rc, const char *token);
void scan_file(const RuleCollection *rc, const char *filename);
void print_banner();
void print_usage(const char *prog_name);
void print_error(const char *message);
void print_success(const char *message);
void print_info(const char *message);
bool is_yaml_file(const char *filename);
void trim_whitespace(char *str);
void print_match_result(const char *filename, char **matches, int match_count);
char* get_current_time();
void print_statistics(const RuleCollection *rc, int tokens_scanned, int total_matches);
void print_separator(int length);

// Helper function to print separator line
void print_separator(int length) {
    for (int i = 0; i < length; i++) {
        printf("=");
    }
    printf("\n");
}

// Initialize rule collection
void init_rule_collection(RuleCollection *rc) {
    rc->files = NULL;
    rc->file_count = 0;
    rc->total_rules = 0;
}

// Free allocated memory
void free_rule_collection(RuleCollection *rc) {
    for (int i = 0; i < rc->file_count; i++) {
        for (int j = 0; j < rc->files[i].count; j++) {
            if (rc->files[i].rules[j].compiled) {
                regfree(&rc->files[i].rules[j].regex);
            }
        }
        free(rc->files[i].rules);
    }
    free(rc->files);
    rc->files = NULL;
    rc->file_count = 0;
    rc->total_rules = 0;
}

// Load rules from a single YAML file
bool load_rules_from_file(RuleCollection *rc, const char *filename) {
    FILE *file = fopen(filename, "r");
    if (!file) {
        return false;
    }

    yaml_parser_t parser;
    yaml_event_t event;
    RuleFile rule_file;
    
    rule_file.rules = malloc(MAX_RULES_PER_FILE * sizeof(PatternRule));
    rule_file.count = 0;
    strncpy(rule_file.filename, filename, MAX_PATH_LEN - 1);
    rule_file.filename[MAX_PATH_LEN - 1] = '\0';

    bool in_patterns = false;
    bool in_pattern = false;
    bool in_name = false;
    bool in_regex = false;
    char current_name[MAX_PATTERN_NAME] = "";
    char current_regex[MAX_LINE_LEN] = "";

    if (!yaml_parser_initialize(&parser)) {
        fclose(file);
        free(rule_file.rules);
        return false;
    }

    yaml_parser_set_input_file(&parser, file);

    bool success = true;
    bool done = false;

    while (!done && yaml_parser_parse(&parser, &event) == 1) {
        switch (event.type) {
            case YAML_STREAM_END_EVENT:
                done = true;
                break;

            case YAML_SCALAR_EVENT:
                {
                    char *value = (char *)event.data.scalar.value;
                    
                    if (strcmp(value, "patterns") == 0) {
                        in_patterns = true;
                    } else if (in_patterns && strcmp(value, "pattern") == 0) {
                        in_pattern = true;
                    } else if (in_pattern && strcmp(value, "name") == 0) {
                        in_name = true;
                    } else if (in_pattern && strcmp(value, "regex") == 0) {
                        in_regex = true;
                    } else if (in_name) {
                        strncpy(current_name, value, MAX_PATTERN_NAME - 1);
                        current_name[MAX_PATTERN_NAME - 1] = '\0';
                        in_name = false;
                    } else if (in_regex) {
                        strncpy(current_regex, value, MAX_LINE_LEN - 1);
                        current_regex[MAX_LINE_LEN - 1] = '\0';
                        in_regex = false;
                        
                        // Compile and add the rule
                        if (strlen(current_regex) > 0 && rule_file.count < MAX_RULES_PER_FILE) {
                            PatternRule *rule = &rule_file.rules[rule_file.count];
                            strncpy(rule->name, current_name, MAX_PATTERN_NAME - 1);
                            rule->name[MAX_PATTERN_NAME - 1] = '\0';
                            
                            // Try to compile regex, but don't show warnings on failure
                            int regex_result = regcomp(&rule->regex, current_regex, REG_EXTENDED);
                            if (regex_result == 0) {
                                rule->compiled = true;
                                rule_file.count++;
                                rc->total_rules++;
                            } else {
                                // Failed to compile - just skip it quietly
                                rule->compiled = false;
                            }
                        }
                        
                        // Reset for next pattern
                        current_name[0] = '\0';
                        current_regex[0] = '\0';
                        in_pattern = false;
                    }
                }
                break;

            default:
                break;
        }

        yaml_event_delete(&event);
    }

    yaml_parser_delete(&parser);
    fclose(file);

    // Add to collection if we found any rules
    if (rule_file.count > 0) {
        rc->files = realloc(rc->files, (rc->file_count + 1) * sizeof(RuleFile));
        rc->files[rc->file_count] = rule_file;
        rc->file_count++;
        return true;
    } else {
        free(rule_file.rules);
        return false;
    }
}

// Load all YAML files from directory
void load_all_rule_files(RuleCollection *rc, const char *dir_path) {
    DIR *dir = opendir(dir_path);
    if (!dir) {
        print_error("Could not open rules directory");
        return;
    }

    struct dirent *entry;
    int files_loaded = 0;

    printf(COLOR_CYAN "Loading rules from %s...\n" COLOR_RESET, dir_path);

    while ((entry = readdir(dir)) != NULL) {
        if (is_yaml_file(entry->d_name)) {
            char full_path[MAX_PATH_LEN];
            snprintf(full_path, sizeof(full_path), "%s/%s", dir_path, entry->d_name);
            
            struct stat path_stat;
            if (stat(full_path, &path_stat) == 0 && S_ISREG(path_stat.st_mode)) {
                if (load_rules_from_file(rc, full_path)) {
                    files_loaded++;
                }
            }
        }
    }

    closedir(dir);
    
    printf(COLOR_GREEN "\n✓ Loaded %d rule files with %d total patterns\n" COLOR_RESET, 
           files_loaded, rc->total_rules);
}

// Check if file is YAML
bool is_yaml_file(const char *filename) {
    size_t len = strlen(filename);
    if (len < 4) return false;
    return (strcmp(filename + len - 4, ".yml") == 0 || 
            strcmp(filename + len - 5, ".yaml") == 0);
}

// Scan a single token against all rules
void scan_token(const RuleCollection *rc, const char *token) {
    printf(COLOR_BOLD "\n%s Scanning token: " COLOR_YELLOW "%s" COLOR_RESET "\n",
           get_current_time(), token);
    
    bool found_any = false;
    int total_matches = 0;

    for (int i = 0; i < rc->file_count; i++) {
        char *matches[MAX_RULES_PER_FILE];
        int match_count = 0;

        for (int j = 0; j < rc->files[i].count; j++) {
            if (!rc->files[i].rules[j].compiled) continue;

            int regex_result = regexec(&rc->files[i].rules[j].regex, token, 0, NULL, 0);
            if (regex_result == 0) {
                matches[match_count] = rc->files[i].rules[j].name;
                match_count++;
                total_matches++;
            }
        }

        if (match_count > 0) {
            found_any = true;
            print_match_result(rc->files[i].filename, matches, match_count);
        }
    }

    if (!found_any) {
        printf(COLOR_RED "\n✗ No matches found\n" COLOR_RESET);
    } else {
        printf(COLOR_GREEN "\n✓ Found %d total matches\n" COLOR_RESET, total_matches);
    }
}

// Scan tokens from a file
void scan_file(const RuleCollection *rc, const char *filename) {
    FILE *file = fopen(filename, "r");
    if (!file) {
        print_error("Could not open input file");
        return;
    }

    char line[MAX_LINE_LEN];
    int tokens_scanned = 0;
    int total_matches = 0;

    printf(COLOR_BOLD "%s Scanning file: %s\n" COLOR_RESET, get_current_time(), filename);

    while (fgets(line, sizeof(line), file)) {
        trim_whitespace(line);
        if (strlen(line) == 0) continue;

        tokens_scanned++;
        
        printf(COLOR_BOLD "\n");
        print_separator(40);
        printf(COLOR_BOLD "Token %d: " COLOR_YELLOW "%s" COLOR_RESET "\n", 
               tokens_scanned, line);

        bool found_any = false;
        int token_matches = 0;

        for (int i = 0; i < rc->file_count; i++) {
            char *matches[MAX_RULES_PER_FILE];
            int match_count = 0;

            for (int j = 0; j < rc->files[i].count; j++) {
                if (!rc->files[i].rules[j].compiled) continue;

                int regex_result = regexec(&rc->files[i].rules[j].regex, line, 0, NULL, 0);
                if (regex_result == 0) {
                    matches[match_count] = rc->files[i].rules[j].name;
                    match_count++;
                    token_matches++;
                    total_matches++;
                }
            }

            if (match_count > 0) {
                found_any = true;
                print_match_result(rc->files[i].filename, matches, match_count);
            }
        }

        if (!found_any) {
            printf(COLOR_RED "  ✗ No matches for this token\n" COLOR_RESET);
        }
    }

    fclose(file);
    
    print_statistics(rc, tokens_scanned, total_matches);
}

// Print match results for a file
void print_match_result(const char *filename, char **matches, int match_count) {
    char base_filename[MAX_PATH_LEN];
    strncpy(base_filename, filename, MAX_PATH_LEN - 1);
    char *last_slash = strrchr(base_filename, '/');
    char *display_name = last_slash ? last_slash + 1 : base_filename;

    printf(COLOR_GREEN "  ✓ " COLOR_CYAN "%s" COLOR_RESET " (%d matches):\n", 
           display_name, match_count);
    
    for (int i = 0; i < match_count; i++) {
        printf(COLOR_YELLOW "    • %s\n" COLOR_RESET, matches[i]);
    }
}

// Remove whitespace from string
void trim_whitespace(char *str) {
    int i = 0, j = 0;
    
    // Skip leading whitespace
    while (isspace((unsigned char)str[i])) i++;
    
    // Copy non-whitespace characters
    while (str[i] != '\0') {
        if (!isspace((unsigned char)str[i]) || 
            (i > 0 && !isspace((unsigned char)str[i-1]))) {
            str[j++] = str[i];
        }
        i++;
    }
    
    // Remove trailing whitespace
    if (j > 0 && isspace((unsigned char)str[j-1])) {
        j--;
    }
    
    str[j] = '\0';
}

// Get current time as string
char* get_current_time() {
    static char time_buf[20];
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    strftime(time_buf, sizeof(time_buf), "%H:%M:%S", tm_info);
    return time_buf;
}

// Print statistics
void print_statistics(const RuleCollection *rc, int tokens_scanned, int total_matches) {
    printf(COLOR_BOLD "\n");
    print_separator(40);
    printf("SCAN COMPLETE\n");
    printf(COLOR_CYAN);
    print_separator(40);
    printf(COLOR_RESET);
    printf(COLOR_BOLD "Statistics:\n" COLOR_RESET);
    printf("  Rule files loaded:  %d\n", rc->file_count);
    printf("  Patterns loaded:    %d\n", rc->total_rules);
    printf("  Tokens scanned:     %d\n", tokens_scanned);
    printf("  Total matches:      %d\n", total_matches);
    
    if (tokens_scanned > 0) {
        float match_rate = (float)total_matches / tokens_scanned * 100;
        printf("  Match rate:         %.1f%%\n", match_rate);
    }
    printf(COLOR_CYAN);
    print_separator(40);
    printf(COLOR_RESET "\n");
}

// Print banner
void print_banner() {
    printf(COLOR_CYAN);
    print_separator(60);
    printf(COLOR_BOLD "                  REGEX PATTERN SCANNER\n" COLOR_RESET);
    printf(COLOR_CYAN);
    print_separator(60);
    printf(COLOR_RESET "\n");
}

// Print usage information
void print_usage(const char *prog_name) {
    printf("Usage:\n");
    printf("  %s <token>                 Scan a single token\n", prog_name);
    printf("  %s -f <file>               Scan tokens from a file\n", prog_name);
    printf("  %s -d <directory>          Use custom rules directory\n", prog_name);
    printf("  %s -h                      Show this help message\n", prog_name);
    printf("\nExamples:\n");
    printf("  %s \"example@email.com\"\n", prog_name);
    printf("  %s -f tokens.txt\n", prog_name);
    printf("  %s -d /path/to/rules -f input.txt\n", prog_name);
}

// Error printing
void print_error(const char *message) {
    fprintf(stderr, COLOR_RED "[ERROR] %s\n" COLOR_RESET, message);
}

void print_success(const char *message) {
    printf(COLOR_GREEN "[SUCCESS] %s\n" COLOR_RESET, message);
}

void print_info(const char *message) {
    printf(COLOR_CYAN "[INFO] %s\n" COLOR_RESET, message);
}

// Main function
int main(int argc, char *argv[]) {
    if (argc < 2) {
        print_banner();
        print_usage(argv[0]);
        return 1;
    }

    // Check for help flag
    if (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0) {
        print_banner();
        print_usage(argv[0]);
        return 0;
    }

    // Determine rules directory
    char rules_dir[MAX_PATH_LEN] = DEFAULT_RULES_DIR;
    
    // Parse command line arguments
    char *input_file = NULL;
    char *token = NULL;
    bool file_mode = false;
    
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-f") == 0 && i + 1 < argc) {
            input_file = argv[i + 1];
            file_mode = true;
            i++;
        } else if (strcmp(argv[i], "-d") == 0 && i + 1 < argc) {
            strncpy(rules_dir, argv[i + 1], MAX_PATH_LEN - 1);
            rules_dir[MAX_PATH_LEN - 1] = '\0';
            i++;
        } else if (i == 1 && argv[i][0] != '-') {
            // If first argument doesn't start with -, treat as token
            token = argv[i];
            // Concatenate remaining arguments for the token
            for (int j = 2; j < argc; j++) {
                // For simplicity, just use first arg
                token = argv[1];
                break;
            }
        }
    }

    print_banner();
    
    // Load rules
    RuleCollection rc;
    init_rule_collection(&rc);
    
    print_info("Loading rules...");
    load_all_rule_files(&rc, rules_dir);
    
    if (rc.file_count == 0) {
        print_error("No valid rule files loaded");
        free_rule_collection(&rc);
        return 1;
    }

    // Perform scan
    if (file_mode && input_file) {
        scan_file(&rc, input_file);
    } else if (token) {
        scan_token(&rc, token);
    } else {
        print_error("No token or file specified");
        print_usage(argv[0]);
        free_rule_collection(&rc);
        return 1;
    }

    // Cleanup
    free_rule_collection(&rc);
    
    return 0;
}