# Claude Code Router Integration Design

## Overview
This design extends the Mattermost bot to support Claude Code Router (CCR) when the `CCR_PROFILE` environment variable is set and the `ccr` command is available. The integration maintains backward compatibility by falling back to the standard `claude` command when conditions aren't met.

## Architecture Changes

### Modified Components
- **ClaudeCodeSession.sendToClaude()** method (lines 739-778)
- **Command selection logic** based on environment and availability
- **Enhanced logging** for transparency

### Key Design Decisions
1. **Robust Command Detection**: Check both `CCR_PROFILE` existence and `ccr` command availability
2. **Graceful Fallback**: Automatic fallback to `claude` when CCR conditions not met
3. **Argument Preservation**: Maintain all existing CLI arguments including permission modes
4. **Backward Compatibility**: No breaking changes for existing deployments

## Implementation Details

### Command Selection Logic
```javascript
const ccrProfile = process.env.CCR_PROFILE;
const useCCR = ccrProfile && ccrProfile.trim() !== '';

// Check ccr command availability
let ccrAvailable = false;
try {
    const { spawnSync } = require('child_process');
    ccrAvailable = spawnSync('which', ['ccr']).status === 0;
} catch (error) {
    console.warn('Failed to check ccr command availability:', error.message);
}

const command = useCCR && ccrAvailable ? 'ccr' : 'claude';
const args = useCCR && ccrAvailable ?
    [ccrProfile, '--permission-mode', permissionMode] :
    ['--permission-mode', permissionMode];
```

### Environment Variables
- **CCR_PROFILE**: Optional, enables CCR usage when set to non-empty value
- **CLAUDE_PERMISSION_MODE**: Preserved unchanged for both commands
- **Existing variables**: No changes required

## Testing Strategy

### Test Scenarios
1. **CCR Available**: `CCR_PROFILE=default` + `ccr` command exists → uses `ccr default`
2. **CCR Unavailable**: `CCR_PROFILE=default` + no `ccr` command → falls back to `claude`
3. **No CCR Profile**: `CCR_PROFILE` not set → uses `claude` (current behavior)
4. **Empty Profile**: `CCR_PROFILE=""` → uses `claude` (treated as not set)

### Validation Criteria
- ✅ Correct command selection based on environment
- ✅ Permission mode preservation for both commands
- ✅ Graceful error handling and fallback
- ✅ No regression in existing functionality
- ✅ Comprehensive logging for observability

## Security Considerations
- Maintains existing input sanitization
- Preserves permission mode validation
- No new security risks introduced
- Command execution remains sandboxed

## Deployment Plan
1. **Development**: Implement and test in isolation
2. **Staging**: Verify CCR integration and fallback scenarios
3. **Production**: Gradual rollout with monitoring

## Success Metrics
- Command usage ratio (CCR vs Claude)
- Fallback occurrence frequency
- Error rates by command type
- User satisfaction with CCR integration

---

*Design approved for implementation on 2026-02-27*