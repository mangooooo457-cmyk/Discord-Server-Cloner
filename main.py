#!/usr/bin/env python3
"""
Discord Server Cloner Selfbot (Educational Use Only)
Author: @ur_daddy619
Description: Clones a server (channels, messages, attachments, roles) using HTTP requests.
Supports PC and Termux. Includes proxy rotation, adaptive rate limits, and smart reuse.
You can specify source channels to skip entirely (they won't be created in target).
"""

import asyncio
import aiohttp
import aiohttp_socks
import json
import sys
import time
import os
import random
import re
from typing import Dict, List, Optional, Any, Tuple

# ----------------------------- CONFIGURATION -----------------------------
MAX_RETRIES = 3
RETRY_DELAY = 5
API_BASE = "https://discord.com/api/v9"
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 MB (Discord webhook limit)
# -------------------------------------------------------------------------

class ProxyManager:
    """Manages proxy rotation for requests."""
    def __init__(self, proxy_type: str, proxy_file: str):
        self.proxy_type = proxy_type.lower()
        self.proxies = self._load_proxies(proxy_file)
        self.index = 0
        self.lock = asyncio.Lock()

    def _load_proxies(self, filename: str) -> List[str]:
        proxies = []
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        proxies.append(line)
        except Exception as e:
            print(f"âŒ Failed to load proxies: {e}")
            sys.exit(1)
        if not proxies:
            print("âŒ No proxies found in file.")
            sys.exit(1)
        print(f"âœ… Loaded {len(proxies)} proxies.")
        return proxies

    async def get_next_proxy(self) -> Optional[str]:
        async with self.lock:
            if not self.proxies:
                return None
            proxy = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            if self.proxy_type in ('http', 'https'):
                return f"{self.proxy_type}://{proxy}"
            elif self.proxy_type == 'socks4':
                return f"socks4://{proxy}"
            elif self.proxy_type == 'socks5':
                return f"socks5://{proxy}"
            else:
                return None

class DiscordAPIClient:
    def __init__(self, token: str, proxy_manager: Optional[ProxyManager] = None):
        self.token = token
        self.proxy_manager = proxy_manager
        self.session = None
        self.headers = {
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get_proxy(self) -> Optional[str]:
        if self.proxy_manager:
            return await self.proxy_manager.get_next_proxy()
        return None

    async def request(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f"{API_BASE}{endpoint}"
        proxy = await self._get_proxy()
        retries = 0
        while retries < 5:
            try:
                async with self.session.request(method, url, proxy=proxy, **kwargs) as resp:
                    if resp.status == 429:
                        data = await resp.json()
                        retry_after = data.get('retry_after', 1)
                        print(f"    â³ Rate limited. Waiting {retry_after:.1f}s...")
                        await asyncio.sleep(retry_after)
                        retries += 1
                        continue
                    elif resp.status in (200, 201, 204):
                        if resp.status == 204:
                            return {}
                        return await resp.json()
                    else:
                        text = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {text}")
            except aiohttp.ClientError as e:
                print(f"    âš  Proxy error: {e}. Trying next proxy...")
                proxy = await self._get_proxy()
                retries += 1
                await asyncio.sleep(1)
                continue
        raise Exception("Too many retries")

    async def get(self, endpoint: str) -> dict:
        return await self.request("GET", endpoint)

    async def post(self, endpoint: str, data: dict = None, json_data: dict = None) -> dict:
        kwargs = {}
        if data:
            kwargs['data'] = data
        if json_data:
            kwargs['json'] = json_data
        return await self.request("POST", endpoint, **kwargs)

    async def delete(self, endpoint: str) -> dict:
        return await self.request("DELETE", endpoint)

    async def patch(self, endpoint: str, json_data: dict) -> dict:
        return await self.request("PATCH", endpoint, json=json_data)

    async def get_guild(self, guild_id: int) -> dict:
        return await self.get(f"/guilds/{guild_id}")

    async def get_guild_channels(self, guild_id: int) -> List[dict]:
        return await self.get(f"/guilds/{guild_id}/channels")

    async def get_guild_roles(self, guild_id: int) -> List[dict]:
        return await self.get(f"/guilds/{guild_id}/roles")

    async def create_role(self, guild_id: int, role_data: dict) -> dict:
        return await self.post(f"/guilds/{guild_id}/roles", json_data=role_data)

    async def get_channel_webhooks(self, channel_id: int) -> List[dict]:
        return await self.get(f"/channels/{channel_id}/webhooks")

    async def delete_channel(self, channel_id: int) -> None:
        await self.delete(f"/channels/{channel_id}")

    async def get_channel_messages(self, channel_id: int, limit: int = 100, before: str = None) -> List[dict]:
        params = {"limit": limit}
        if before:
            params["before"] = before
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return await self.get(f"/channels/{channel_id}/messages?{query}")

    async def create_guild(self, name: str) -> dict:
        return await self.post("/guilds", json_data={"name": name})

    async def create_channel(self, guild_id: int, channel_data: dict) -> dict:
        return await self.post(f"/guilds/{guild_id}/channels", json_data=channel_data)

    async def create_webhook(self, channel_id: int, name: str) -> dict:
        return await self.post(f"/channels/{channel_id}/webhooks", json_data={"name": name})

    async def get_webhook_url(self, webhook_id: int, token: str) -> str:
        return f"https://discord.com/api/webhooks/{webhook_id}/{token}"

    async def send_webhook(self, webhook_url: str, data: dict, files: List[Tuple[str, bytes]] = None) -> None:
        proxy = await self._get_proxy()
        if files:
            form = aiohttp.FormData()
            payload_json_data = {
                "content": data.get("content", ""),
                "username": data.get("username"),
                "avatar_url": data.get("avatar_url"),
                "embeds": data.get("embeds", [])
            }
            payload_json_data = {k: v for k, v in payload_json_data.items() if v is not None}
            form.add_field('payload_json', json.dumps(payload_json_data), content_type='application/json')
            for idx, (filename, file_data) in enumerate(files):
                form.add_field('file', file_data, filename=filename, content_type='application/octet-stream')
            async with self.session.post(webhook_url, data=form, proxy=proxy) as resp:
                if resp.status not in (200, 204):
                    text = await resp.text()
                    raise Exception(f"Webhook send failed: {resp.status} - {text}")
        else:
            async with self.session.post(webhook_url, json=data, proxy=proxy) as resp:
                if resp.status not in (200, 204):
                    text = await resp.text()
                    raise Exception(f"Webhook send failed: {resp.status} - {text}")

class ServerCloner:
    def __init__(self, token: str, source_guild_id: int, target_guild_id: int = None,
                 proxy_manager: Optional[ProxyManager] = None,
                 webhook_count: int = 1,
                 base_delay: float = 3.0,
                 channel_delay: float = 0.5,
                 msg_delay: float = 0.05,
                 skip_channel_ids: List[int] = None,
                 purge_command: str = "&purge all"):
        self.token = token
        self.source_guild_id = source_guild_id
        self.target_guild_id = target_guild_id
        self.proxy_manager = proxy_manager
        self.webhook_count = webhook_count
        self.base_delay = base_delay
        self.current_delay = base_delay
        self.channel_delay = channel_delay
        self.msg_delay = msg_delay
        self.skip_channel_ids = skip_channel_ids or []
        self.purge_command = purge_command
        self.api = None
        self.source_guild = None
        self.target_guild = None
        self.channel_map = {}          # source_channel_id -> target_channel_id
        self.category_map = {}         # source_category_id -> target_category_id
        self.webhook_queues = {}       # source_channel_id -> list of webhook URLs
        self.webhook_index = {}        # source_channel_id -> current index
        self.role_map = {}             # source_role_id -> target_role_id
        self.stats = {
            "channels_created": 0,
            "channels_reused": 0,
            "webhooks_created": 0,
            "webhooks_reused": 0,
            "messages_copied": 0,
            "roles_created": 0,
            "channels_skipped": 0
        }

    async def run(self):
        print("\n" + "="*60)
        print("   ðŸš€ Discord Server Cloner Selfbot ðŸš€   ")
        print("           by @ur_daddy619            ")
        print("        EDUCATIONAL PURPOSE ONLY    ")
        print("="*60 + "\n")

        print("ðŸ” [0/7] Validating token...")
        async with DiscordAPIClient(self.token, self.proxy_manager) as api:
            self.api = api
            try:
                me = await api.get("/users/@me")
                print(f"âœ… Logged in as {me['username']}#{me.get('discriminator', '0')} (ID: {me['id']})")
            except Exception as e:
                print(f"âŒ Invalid token: {e}")
                return

            # Source server
            print(f"\nðŸ“‚ [1/7] Fetching source server...")
            try:
                self.source_guild = await api.get_guild(self.source_guild_id)
                print(f"âœ… Source server: {self.source_guild['name']} (ID: {self.source_guild['id']})")
            except Exception as e:
                print(f"âŒ Could not find server: {e}")
                return

            # Target server
            if self.target_guild_id:
                print(f"\nðŸŽ¯ [2/7] Using existing target server...")
                try:
                    self.target_guild = await api.get_guild(self.target_guild_id)
                    print(f"âœ… Target server: {self.target_guild['name']} (ID: {self.target_guild['id']})")
                except Exception as e:
                    print(f"âŒ Could not find target server: {e}")
                    return
            else:
                new_guild_name = f"{self.source_guild['name']} - Clone"
                print(f"\nðŸ—ï¸ [2/7] Creating new server '{new_guild_name}'...")
                self.target_guild = await self.create_guild_with_retry(new_guild_name)
                if not self.target_guild:
                    print("âŒ Failed to create server after retries.")
                    print("\nðŸ’¡ Possible reasons:")
                    print("   â€¢ You already have 100 servers (max limit).")
                    print("   â€¢ Your account is new or hasn't verified phone number.")
                    print("   â€¢ Discord has temporarily restricted your account.")
                    print("\nðŸ‘‰ You can create a server manually and provide its ID to clone into it.")
                    choice = input("Do you want to try cloning into an existing server? (y/n): ").strip().lower()
                    if choice == 'y':
                        target_id = int(input("Enter the target server ID: ").strip())
                        self.target_guild = await self.check_existing_server(target_id)
                        if not self.target_guild:
                            print("âŒ Cannot proceed. Exiting.")
                            return
                    else:
                        return
                else:
                    print(f"âœ… New server created: {self.target_guild['name']} (ID: {self.target_guild['id']})")

            # Cleanup / reuse choice
            cleanup = input("\nðŸ§¹ Delete all existing channels in target server before cloning? (y/n, default n): ").strip().lower() == 'y'
            if cleanup:
                print(f"\nðŸ§¹ [3/7] Cleaning target server channels...")
                await self.delete_all_channels()
                existing_target_channels = {}
            else:
                print(f"\nðŸ” [3/7] Fetching existing target channels...")
                existing_target_channels = await self.fetch_existing_channels()

            # Ask for skip channels (source channels to completely omit)
            print("\nâ­ï¸  Enter source channel IDs to SKIP ENTIRELY (they won't be created in target).")
            try:
                skip_count = int(input("How many channels to skip? (0 if none): ").strip() or "0")
            except:
                skip_count = 0
            skip_ids = []
            if skip_count > 0:
                print(f"Enter {skip_count} source channel ID(s) to skip (press Enter after each):")
                for i in range(skip_count):
                    while True:
                        inp = input(f"  Channel ID {i+1}: ").strip()
                        if not inp:
                            print("  âŒ ID cannot be empty, try again.")
                            continue
                        try:
                            sid = int(inp)
                            skip_ids.append(sid)
                            break
                        except ValueError:
                            print("  âŒ Invalid ID, try again.")
            self.skip_channel_ids = skip_ids
            if self.skip_channel_ids:
                print(f"â„¹ï¸ Will skip {len(self.skip_channel_ids)} channel(s) entirely (not created).")

            # Ask for purge command (if not cleaning)
            if not cleanup:
                purge_cmd = input("\nðŸ§¹ Enter the command to clear channels (default '&purge all'): ").strip()
                if purge_cmd:
                    self.purge_command = purge_cmd
                print(f"â„¹ï¸ Will send '{self.purge_command}' in every text channel after cloning.")

            # Copy roles
            print(f"\nðŸ‘¥ [4/7] Copying roles...")
            await self.copy_roles()

            # Copy channel structure (with reuse and skipping)
            print(f"\nðŸ“ [5/7] Copying channel structure...")
            await self.copy_channel_structure(existing_target_channels)

            # Now that we have target channel IDs, fetch existing webhooks for reused channels
            if not cleanup:
                print(f"\nðŸ” [6/7] Fetching existing webhooks for reused channels...")
                existing_webhooks = await self.fetch_existing_webhooks()
            else:
                existing_webhooks = {}

            # Create/Reuse webhooks
            print(f"\nðŸ”— [7/7] Preparing {self.webhook_count} webhooks per channel...")
            await self.create_webhooks(existing_webhooks)

            # Copy messages (skip specified channels)
            print(f"\nðŸ’¬ Copying messages (this may take a while)...")
            await self.copy_all_messages()

            # Purge command if not cleaned
            if not cleanup:
                print(f"\nðŸ§¹ Sending purge command '{self.purge_command}' in all text channels...")
                await self.send_purge_command()

            # Summary
            print("\n" + "="*60)
            print("ðŸŽ‰âœ… CLONING COMPLETE! âœ…ðŸŽ‰")
            print("="*60)
            print(f"ðŸ“Š Statistics:")
            print(f"   â€¢ Roles created:        {self.stats['roles_created']}")
            print(f"   â€¢ Channels created:     {self.stats['channels_created']}")
            print(f"   â€¢ Channels reused:      {self.stats['channels_reused']}")
            print(f"   â€¢ Channels skipped:     {self.stats['channels_skipped']}")
            print(f"   â€¢ Webhooks created:     {self.stats['webhooks_created']}")
            print(f"   â€¢ Webhooks reused:      {self.stats['webhooks_reused']}")
            print(f"   â€¢ Messages copied:      {self.stats['messages_copied']}")
            print("="*60)

    async def check_existing_server(self, guild_id: int) -> Optional[dict]:
        try:
            guild = await self.api.get_guild(guild_id)
            print(f"âœ… Using existing server: {guild['name']} (ID: {guild['id']})")
            return guild
        except Exception as e:
            print(f"âŒ Could not find server: {e}")
            return None

    async def create_guild_with_retry(self, name: str) -> Optional[dict]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                guild = await self.api.create_guild(name)
                await asyncio.sleep(2)
                return guild
            except Exception as e:
                err_str = str(e)
                if "403" in err_str:
                    print(f"  âŒ Cannot create server: {err_str}")
                    return None
                elif "429" in err_str or "rate limited" in err_str.lower():
                    print(f"  â³ Rate limited (attempt {attempt}/{MAX_RETRIES}). Waiting {RETRY_DELAY}s...")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"  âŒ Failed to create guild: {e}")
                    return None
        return None

    async def delete_all_channels(self):
        channels = await self.api.get_guild_channels(self.target_guild['id'])
        for ch in reversed(channels):
            try:
                await self.api.delete_channel(ch['id'])
                await asyncio.sleep(0.2)
                print(f"  ðŸ—‘ï¸ Deleted {ch['name']} (type: {ch['type']})")
            except Exception as e:
                print(f"  âš  Failed to delete {ch['name']}: {e}")
        print("  âœ… Cleanup finished.")

    async def fetch_existing_channels(self) -> Dict[str, int]:
        """Returns dict of channel name (lowercase) -> channel id for existing target channels."""
        channels = await self.api.get_guild_channels(self.target_guild['id'])
        name_to_id = {}
        for ch in channels:
            name_to_id[ch['name'].lower()] = ch['id']
        print(f"  ðŸ“‹ Found {len(name_to_id)} existing channels.")
        return name_to_id

    async def fetch_existing_webhooks(self) -> Dict[int, List[str]]:
        """Returns dict of target_channel_id -> list of webhook URLs for channels that were reused."""
        webhook_map = {}
        # Only fetch for channels we reused (i.e., those in channel_map values)
        target_channel_ids = set(self.channel_map.values())
        print(f"  ðŸ” Checking {len(target_channel_ids)} reused channel(s) for existing webhooks...")
        for ch_id in target_channel_ids:
            try:
                webhooks = await self.api.get_channel_webhooks(ch_id)
                urls = []
                for wh in webhooks:
                    url = await self.api.get_webhook_url(wh['id'], wh['token'])
                    urls.append(url)
                if urls:
                    webhook_map[ch_id] = urls
                    print(f"    âœ… Found {len(urls)} webhook(s) in channel {ch_id}")
                else:
                    print(f"    â„¹ï¸ No webhooks in channel {ch_id}")
            except Exception as e:
                print(f"    âš  Failed to fetch webhooks for channel {ch_id}: {e}")
        return webhook_map

    async def copy_roles(self):
        """Copy all roles from source to target."""
        source_roles = await self.api.get_guild_roles(self.source_guild_id)
        target_roles = await self.api.get_guild_roles(self.target_guild['id'])
        existing_names = {r['name'].lower(): r['id'] for r in target_roles}
        for src_role in source_roles:
            if src_role['id'] == self.source_guild_id:
                continue
            role_name = src_role['name']
            if role_name.lower() in existing_names:
                self.role_map[src_role['id']] = existing_names[role_name.lower()]
                print(f"  ðŸ”„ Reusing role: {role_name}")
                continue
            role_data = {
                "name": role_name,
                "color": src_role.get('color', 0),
                "hoist": src_role.get('hoist', False),
                "mentionable": src_role.get('mentionable', False),
                "permissions": src_role.get('permissions', '0')
            }
            try:
                new_role = await self.api.create_role(self.target_guild['id'], role_data)
                self.role_map[src_role['id']] = new_role['id']
                self.stats['roles_created'] += 1
                print(f"  âœ… Created role: {role_name}")
                await asyncio.sleep(self.channel_delay)
            except Exception as e:
                print(f"  âŒ Failed to create role {role_name}: {e}")

    async def copy_channel_structure(self, existing_channels: Dict[str, int]):
        source_channels = await self.api.get_guild_channels(self.source_guild_id)

        # First, map categories
        for src_ch in source_channels:
            if src_ch['type'] == 4:
                if src_ch['id'] in self.skip_channel_ids:
                    print(f"  â­ï¸ Skipping category (user excluded): {src_ch['name']}")
                    self.stats['channels_skipped'] += 1
                    continue
                name = src_ch['name']
                if name.lower() in existing_channels:
                    target_cat_id = existing_channels[name.lower()]
                    self.category_map[src_ch['id']] = target_cat_id
                    self.stats['channels_reused'] += 1
                    print(f"  ðŸ”„ Reusing category: {name}")
                else:
                    try:
                        data = {
                            "name": name,
                            "type": 4,
                            "position": src_ch.get('position', 0)
                        }
                        if src_ch.get('permission_overwrites'):
                            data["permission_overwrites"] = self._map_permissions(src_ch['permission_overwrites'])
                        new_cat = await self.api.create_channel(self.target_guild['id'], data)
                        self.category_map[src_ch['id']] = new_cat['id']
                        self.stats['channels_created'] += 1
                        print(f"  ðŸ“ Created category: {name}")
                        await asyncio.sleep(self.channel_delay)
                    except Exception as e:
                        print(f"  âŒ Failed to create category {name}: {e}")

        # Then copy text and voice channels
        for src_ch in source_channels:
            if src_ch['type'] in (0, 2, 5):
                if src_ch['id'] in self.skip_channel_ids:
                    print(f"  â­ï¸ Skipping {'Text' if src_ch['type']==0 else 'Voice'} channel (user excluded): {src_ch['name']}")
                    self.stats['channels_skipped'] += 1
                    continue
                name = src_ch['name']
                if name.lower() in existing_channels:
                    target_ch_id = existing_channels[name.lower()]
                    self.channel_map[src_ch['id']] = target_ch_id
                    self.stats['channels_reused'] += 1
                    icon = "ðŸ’¬" if src_ch['type'] == 0 else "ðŸŽ¤"
                    print(f"  {icon} Reusing {'Text' if src_ch['type']==0 else 'Voice'} channel: {name}")
                else:
                    try:
                        data = {
                            "name": name,
                            "type": src_ch['type'],
                            "position": src_ch.get('position', 0)
                        }
                        if src_ch.get('permission_overwrites'):
                            data["permission_overwrites"] = self._map_permissions(src_ch['permission_overwrites'])
                        if src_ch.get('topic'):
                            data["topic"] = src_ch['topic']
                        if src_ch.get('nsfw'):
                            data["nsfw"] = src_ch['nsfw']
                        if src_ch.get('rate_limit_per_user'):
                            data["rate_limit_per_user"] = src_ch['rate_limit_per_user']
                        if src_ch.get('bitrate'):
                            data["bitrate"] = src_ch['bitrate']
                        if src_ch.get('user_limit'):
                            data["user_limit"] = src_ch['user_limit']
                        if src_ch.get('parent_id') and src_ch['parent_id'] in self.category_map:
                            data["parent_id"] = self.category_map[src_ch['parent_id']]

                        new_ch = await self.api.create_channel(self.target_guild['id'], data)
                        if src_ch['type'] == 0:
                            self.channel_map[src_ch['id']] = new_ch['id']
                        self.stats['channels_created'] += 1
                        icon = "ðŸ’¬" if src_ch['type'] == 0 else "ðŸŽ¤"
                        print(f"  {icon} Created {'Text' if src_ch['type']==0 else 'Voice'} channel: {name}")
                        await asyncio.sleep(self.channel_delay)
                    except Exception as e:
                        print(f"  âŒ Failed to create channel {name}: {e}")

    def _map_permissions(self, overwrites):
        """Map permission overwrites to use target role IDs."""
        if not overwrites:
            return overwrites
        mapped = []
        for ow in overwrites:
            ow_copy = ow.copy()
            if ow.get('type') == 0:  # role
                src_role_id = int(ow['id'])
                if src_role_id in self.role_map:
                    ow_copy['id'] = str(self.role_map[src_role_id])
            mapped.append(ow_copy)
        return mapped

    async def create_webhooks(self, existing_webhooks: Dict[int, List[str]]):
        """Create or reuse webhooks for each text channel."""
        self.current_delay = self.base_delay

        for src_id, target_ch_id in self.channel_map.items():
            # Check if channel already has webhooks (from existing_webhooks)
            existing = existing_webhooks.get(target_ch_id, [])
            webhooks = existing[:self.webhook_count]
            # Create additional if needed
            need = self.webhook_count - len(webhooks)
            for i in range(need):
                try:
                    webhook_data = await self.api.create_webhook(target_ch_id, f"Cloner_{i+1}")
                    webhook_url = await self.api.get_webhook_url(webhook_data['id'], webhook_data['token'])
                    webhooks.append(webhook_url)
                    self.stats['webhooks_created'] += 1
                    self.current_delay = max(self.base_delay, self.current_delay * 0.9)
                    actual_delay = self.current_delay * (0.8 + 0.4 * random.random())
                    print(f"    â±ï¸  Waiting {actual_delay:.2f}s before next webhook...")
                    await asyncio.sleep(actual_delay)
                except Exception as e:
                    err_str = str(e)
                    if "403" in err_str:
                        print(f"  âŒ No permission to create webhook in channel {target_ch_id}. Skipping channel.")
                        break
                    elif "429" in err_str:
                        print(f"  â³ Rate limited! Increasing delay...")
                        self.current_delay = min(10.0, self.current_delay * 2)
                        match = re.search(r'retry_after["\']?\s*:\s*([\d.]+)', err_str)
                        if match:
                            retry_after = float(match.group(1))
                            print(f"    â³ Rate limited. Waiting {retry_after:.1f}s...")
                            await asyncio.sleep(retry_after)
                            continue
                        await asyncio.sleep(self.current_delay)
                    else:
                        print(f"  âŒ Failed to create webhook for channel {target_ch_id}: {e}")
            self.webhook_queues[src_id] = webhooks
            self.webhook_index[src_id] = 0
            reused_count = len(existing[:self.webhook_count])
            if reused_count:
                self.stats['webhooks_reused'] += reused_count
                print(f"  ðŸ”„ Reused {reused_count} webhooks for channel {target_ch_id}")
            if webhooks:
                print(f"  âœ… Total {len(webhooks)} webhooks for channel {target_ch_id}")

    async def copy_all_messages(self):
        tasks = []
        for src_ch_id, target_ch_id in self.channel_map.items():
            # Skip if source channel ID is in skip list (already won't be in channel_map if skipped, but double-check)
            if src_ch_id in self.skip_channel_ids:
                print(f"  â­ï¸ Skipping messages for channel {src_ch_id} (user requested).")
                continue
            tasks.append(self.copy_channel_messages(src_ch_id, target_ch_id))
        await asyncio.gather(*tasks)

    async def copy_channel_messages(self, src_ch_id: int, target_ch_id: int):
        print(f"  â†’ Starting to copy messages from channel {src_ch_id}...")
        webhooks = self.webhook_queues.get(src_ch_id, [])
        if not webhooks:
            print(f"    âš  No webhooks for channel {src_ch_id}, skipping.")
            return

        last_message_id = None
        count = 0
        while True:
            try:
                messages = await self.api.get_channel_messages(src_ch_id, limit=100, before=last_message_id)
                if not messages:
                    break

                for msg in reversed(messages):
                    idx = self.webhook_index[src_ch_id] % len(webhooks)
                    webhook_url = webhooks[idx]
                    self.webhook_index[src_ch_id] = idx + 1

                    payload = {
                        "content": msg.get('content', ''),
                        "username": msg['author'].get('global_name') or msg['author']['username'],
                        "avatar_url": f"https://cdn.discordapp.com/avatars/{msg['author']['id']}/{msg['author']['avatar']}.png" if msg['author'].get('avatar') else None,
                        "embeds": msg.get('embeds', [])
                    }

                    files_to_send = []
                    if msg.get('attachments'):
                        for att in msg['attachments']:
                            if att.get('size', 0) > MAX_FILE_SIZE:
                                print(f"      âš  Skipping {att['filename']} ({att['size']} bytes > 8MB limit)")
                                continue
                            try:
                                async with self.api.session.get(att['url']) as resp:
                                    if resp.status == 200:
                                        data = await resp.read()
                                        files_to_send.append((att['filename'], data))
                                    else:
                                        print(f"      âš  Failed to download {att['filename']} (HTTP {resp.status})")
                            except Exception as e:
                                print(f"      âš  Error downloading {att['filename']}: {e}")

                    try:
                        await self.api.send_webhook(webhook_url, payload, files=files_to_send if files_to_send else None)
                        count += 1
                        if count % 100 == 0:
                            print(f"    Copied {count} messages from channel {src_ch_id}")
                        await asyncio.sleep(self.msg_delay)
                    except Exception as e:
                        print(f"      âŒ Failed to send message: {e}")

                last_message_id = messages[-1]['id']
            except Exception as e:
                print(f"    âŒ Error fetching messages: {e}")
                break

        self.stats['messages_copied'] += count
        print(f"  âœ… Finished copying {count} messages from channel {src_ch_id}")

    async def send_purge_command(self):
        """Send the purge command in every text channel using its first webhook."""
        for src_id, target_ch_id in self.channel_map.items():
            webhooks = self.webhook_queues.get(src_id, [])
            if not webhooks:
                print(f"  âš  No webhook for channel {target_ch_id}, skipping purge.")
                continue
            webhook_url = webhooks[0]
            payload = {
                "content": self.purge_command,
                "username": "Cloner Bot"
            }
            try:
                await self.api.send_webhook(webhook_url, payload)
                print(f"  âœ… Sent '{self.purge_command}' in channel {target_ch_id}")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"  âŒ Failed to send purge command in channel {target_ch_id}: {e}")

async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Usage: python cloner.py")
        print("Then follow prompts.")
        return

    token = input("ðŸ”‘ Enter your Discord user token: ").strip()
    if not token:
        print("âŒ No token entered.")
        return

    try:
        source_id = int(input("ðŸ“‚ Enter the source server ID to clone: ").strip())
    except ValueError:
        print("âŒ Invalid server ID.")
        return

    # Proxy configuration
    proxy_manager = None
    use_proxy = input("ðŸŒ Use proxies? (y/n, default n): ").strip().lower() == 'y'
    if use_proxy:
        proxy_type = input("Proxy type (http/https/socks4/socks5): ").strip().lower()
        if proxy_type not in ('http', 'https', 'socks4', 'socks5'):
            print("âŒ Invalid proxy type.")
            return
        proxy_file = input("ðŸ“ Proxy file path (one ip:port per line): ").strip()
        if not os.path.exists(proxy_file):
            print("âŒ Proxy file not found.")
            return
        try:
            if proxy_type.startswith('socks'):
                import aiohttp_socks
            proxy_manager = ProxyManager(proxy_type, proxy_file)
        except ImportError:
            print("âŒ aiohttp_socks is required for SOCKS proxies. Install with: pip install aiohttp-socks")
            return

    # Rate limit delay configuration
    try:
        webhook_count = int(input("ðŸ”§ Number of webhooks per channel (1-4, default 1): ").strip() or "1")
        webhook_count = max(1, min(4, webhook_count))
    except:
        webhook_count = 1

    try:
        base_delay = float(input("ðŸ”§ Base delay between webhook creations (seconds, default 3): ").strip() or "3")
        base_delay = max(1, base_delay)
    except:
        base_delay = 3.0

    try:
        channel_delay = float(input("ðŸ”§ Delay between channel creations (seconds, default 0.5): ").strip() or "0.5")
        channel_delay = max(0.1, channel_delay)
    except:
        channel_delay = 0.5

    try:
        msg_delay = float(input("ðŸ”§ Delay between message sends (seconds, default 0.05): ").strip() or "0.05")
        msg_delay = max(0.01, msg_delay)
    except:
        msg_delay = 0.05

    target_id = None
    use_existing = input("ðŸŽ¯ Do you want to clone into an existing server? (y/n, default n): ").strip().lower()
    if use_existing == 'y':
        try:
            target_id = int(input("Enter the target server ID: ").strip())
        except ValueError:
            print("âŒ Invalid target ID. Will attempt to create a new server.")
            target_id = None

    cloner = ServerCloner(token, source_id, target_id, proxy_manager,
                          webhook_count, base_delay, channel_delay, msg_delay)
    await cloner.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nâŒ Operation cancelled.")
    except Exception as e:
        print(f"\nâŒ Fatal error: {e}")
