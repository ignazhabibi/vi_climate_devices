

# Library Code Protection

## CRITICAL RULE
**I am STRICTLY FORBIDDEN from modifying files in the separate `vi_api_client` library repository as part of this integration workflow**

Even though you own both projects, the library is a separate codebase that requires:
- Version management
- Independent testing
- Coordination between projects

## My Responsibility
When I identify a need for library changes, I must:

1. **STOP** before making any edits to library files
2. **INFORM YOU** with:
   - What needs to be changed and why
   - Suggested implementation approach
   - Which files need modification
   - What version bump is needed
3. **WAIT** for you to make the library changes
4. **THEN** update the integration (manifest.json, tests, etc.)

## Examples

### ✅ Correct Approach:
1. I identified: "MockViClient doesn't recognize Vitocal devices as heating type"
2. I should have informed you: "We need to add DEVICE_TYPE_MAP to mock_client.py"
3. You make the library changes and bump the library to an appropriate new version
4. I update manifest.json and simplify test_analytics.py

### ❌ Wrong Approach:
- I directly edit library source files in the `vi_api_client` repository
- I create commits in the library repository
- I modify library code without explicitly asking you first

## Scope
- **Integration files**: Files in this repository - I CAN modify
- **Library files**: Files in the separate `vi_api_client` repository - I CANNOT modify (INFORM YOU instead)

## Key Principle
**"Inform, don't modify"** - My role is to identify what needs to change in the library and let you handle the actual modifications.
