import sys
import json

def main():
    try:
        # Read JSON payload from stdin
        input_data = sys.stdin.read()
        if not input_data.strip():
            sys.exit(0)
            
        data = json.loads(input_data)
        tool_call = data.get("toolCall", {})
        args = tool_call.get("args", {})
        cmd = args.get("CommandLine", "")
        
        # Blocklist for destructive patterns (e.g. rm -rf, del /s, rmdir /s)
        blocklist = [
            "rm -rf",
            "rmdir /s",
            "del /s",
            "format ",
            "mkfs",
            "dd if="
        ]
        
        cmd_lower = cmd.lower()
        for pattern in blocklist:
            if pattern in cmd_lower:
                sys.stderr.write(f"Security Alert: Destructive command '{cmd}' is blocked by security policy.\n")
                sys.exit(2)
                
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Error in tool validator: {str(e)}\n")
        sys.exit(2)

if __name__ == "__main__":
    main()
