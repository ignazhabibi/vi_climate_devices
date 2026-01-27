

# Library Code Protection

## CRITICAL RULE
**I am STRICTLY FORBIDDEN from modifying any files in `/Users/michael/Projekte/vi_api_client/`**

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

### ✅ Correct Approach (What YOU did for v0.3.4):
1. I identified: "MockViClient doesn't recognize Vitocal devices as heating type"
2. I should have informed you: "We need to add DEVICE_TYPE_MAP to mock_client.py"
3. You make the library changes and bump to v0.3.4
4. I update manifest.json and simplify test_analytics.py

### ❌ Wrong Approach:
- I directly edit `/Users/michael/Projekte/vi_api_client/src/vi_api_client/mock_client.py`
- I create commits in the library repository
- I modify library code without explicitly asking you first

## Scope
- **Integration files**: `/Users/michael/Projekte/vi_climate_devices/` - I CAN modify
- **Library files**: `/Users/michael/Projekte/vi_api_client/` - I CANNOT modify (INFORM YOU instead)

## Key Principle
**"Inform, don't modify"** - My role is to identify what needs to change in the library and let you handle the actual modifications.
