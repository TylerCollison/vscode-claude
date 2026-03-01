# Mattermost Channel Creation Design

## Overview
Modify the `mattermost-initial-post.sh` script to create a new Mattermost channel instead of posting to an existing channel, then configure the channel header and add the bot user.

## Goals
1. Create a new Mattermost channel using `MM_CHANNEL` environment variable as the channel name
2. Set the channel header using the content currently posted as a message
3. Add the bot user to the newly created channel
4. Update `/config/.config/claude-threads/config.yaml` to use the new channel ID

## Architecture

### Functions to Add/Modify

#### `create_mattermost_channel(team_id, channel_name, mm_token)`
- **Purpose**: Create a new public channel in the specified team
- **API**: `POST /api/v4/channels`
- **Payload**: `{"team_id": "...", "name": "...", "display_name": "...", "type": "O"}`
- **Returns**: Channel ID from response

#### `update_channel_header(channel_id, header, mm_token)`
- **Purpose**: Set the channel header with formatted device information
- **API**: `PUT /api/v4/channels/{channel_id}`
- **Header format**: Current message content (Prompt, IDE Address, timestamp)

#### `add_user_to_channel(channel_id, user_id, mm_token)`
- **Purpose**: Add the bot user as a channel member
- **API**: `POST /api/v4/channels/{channel_id}/members`
- **Note**: May need to get bot user ID from token or environment

#### `get_user_id(mm_token)`
- **Purpose**: Resolve the user ID from the access token
- **API**: `GET /api/v4/users/me`
- **Returns**: User ID for adding to channel

#### `update_config_file(channel_id)`
- **Purpose**: Replace `${MM_CHANNEL_ID}` placeholder in config.yaml
- **Implementation**: Use sed to do in-place replacement
- **Path**: `/config/.config/claude-threads/config.yaml`

### Data Flow

```
1. Validate env vars (MM_ADDRESS, MM_CHANNEL, MM_TOKEN, PROMPT, IDE_ADDRESS)
2. Get team ID from MM_TEAM (default: home)
3. Create channel with name from MM_CHANNEL
4. Get bot user ID from token
5. Add bot user to the new channel
6. Update channel header with device info
7. Write channel ID to /tmp/mm_channel_id (for reference)
8. Replace ${MM_CHANNEL_ID} in config.yaml with actual channel ID
9. Log success
```

## Error Handling

- **Channel creation fails**: Exit with error, log Mattermost API response
- **Channel already exists**: Check if channel exists first, or handle 409 conflict
- **User already in channel**: API should return success or be idempotent
- **Config update fails**: Log warning but don't fail (channel is already created)

## Channel Naming

- Use `MM_CHANNEL` env var directly as the channel name
- Channel names in Mattermost must be lowercase alphanumeric with hyphens
- Sanitize: lowercase, replace spaces with hyphens, remove special chars

## Header Format

Set channel header to markdown content:

```
Claude Code Development Environment | Prompt: {PROMPT} | IDE: {IDE_ADDRESS} | Started: {timestamp}
```

Header has limited length, so keep concise.

## Security Considerations

- Token is passed via env var, never logged
- Config file update uses proper file permissions
- Channel created as public (type "O") for visibility

## Testing Checklist

- [ ] Channel creates successfully with sanitized name
- [ ] Channel header displays correctly
- [ ] Bot user is added as member
- [ ] config.yaml gets updated with actual channel ID
- [ ] Script fails gracefully if Mattermost is unreachable
- [ ] Handles channel name collision appropriately
