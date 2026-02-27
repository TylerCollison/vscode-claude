# Mattermost Bot Relocation Design

## Overview
Move `mattermost-bot.js` from `/workspace` to root directory (`/`) while ensuring it runs in the `DEFAULT_WORKSPACE` directory.

## Design Decisions

### Approach Selected
**Approach 1**: Copy to Root + Change Working Directory
- Move `mattermost-bot.js` to `/` (root directory)
- Update startup script to `cd` into `$DEFAULT_WORKSPACE` before execution
- Ensures bot runs in correct working directory context

### Dependency Strategy
**Option 2**: Install dependencies in `/node_modules`
- Install `ws` dependency in `/node_modules` instead of `/workspace/node_modules`
- Bot at `/mattermost-bot.js` can reference `/node_modules/ws`
- Clean separation of concerns

## Implementation Plan

### Phase 1: Dockerfile Changes
1. **Relocate bot file**: Change `COPY mattermost-bot.js /workspace/mattermost-bot.js` to `COPY mattermost-bot.js /mattermost-bot.js`
2. **Update dependency installation**: Change `RUN cd /workspace && npm install...` to `RUN npm install --prefix / --production --no-audit --save-exact ws@8.14.2`
3. **Remove workspace reference**: Remove the workspace-specific installation

### Phase 2: Startup Script Changes
1. **Set working directory**: Add `cd "$DEFAULT_WORKSPACE"` before executing the bot
2. **Update file reference**: Change `/workspace/mattermost-bot.js` to `/mattermost-bot.js`
3. **Add validation**: Check if `DEFAULT_WORKSPACE` is set and directory exists

### Phase 3: Bot Code Verification
1. **Check relative paths**: Verify bot doesn't rely on `/workspace`-specific paths
2. **Test execution**: Ensure bot runs correctly from `DEFAULT_WORKSPACE`

## Files to Modify

### Dockerfile
- Line 48: `COPY mattermost-bot.js /workspace/mattermost-bot.js` → `COPY mattermost-bot.js /mattermost-bot.js`
- Line 51: `RUN cd /workspace && npm install...` → `RUN npm install --prefix / --production...`

### start-mattermost-bot.sh
- Line 73: File existence check path update
- Line 80: Execution command path update
- Add working directory change before execution

## Success Criteria
- Bot file exists at `/mattermost-bot.js`
- Dependencies installed in `/node_modules`
- Startup script runs bot from `$DEFAULT_WORKSPACE`
- Bot functionality remains unchanged

## Risk Assessment
- **Low risk**: File relocation and dependency path changes
- **Medium risk**: Working directory context changes (test thoroughly)
- **Mitigation**: Comprehensive testing of bot functionality

## Testing Plan
1. Build updated Docker image
2. Verify file locations: `/mattermost-bot.js` and `/node_modules/ws`
3. Test bot startup with `DEFAULT_WORKSPACE` set
4. Validate bot functionality remains intact

---
*Design approved: 2026-02-27*
*Implementation to follow design specifications*