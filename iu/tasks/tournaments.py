"""Utility module for generating and posting native Discord polls for tournament matchups."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import tasks
from db.merch import modify_db_balance
from db.tournaments import (
    check_round_status, get_expired_unresolved_matches, advance_winner,
    get_unpolled_matches, set_match_poll_data, get_tournament_days,
    get_tournament_winner_name, get_tournament_raffle_winner, get_active_tournament_id,
    set_tournament_completed
)
from ui.bracket_renderer import generate_bracket_image

logger = logging.getLogger('iu-bot')

async def post_round_polls(channel: discord.TextChannel, tournament_id: str, round_num: int, days_per_round: int):
    """
    Iterates through unpolled matches, creates native Discord polls, and updates the database.
    """
    matches = get_unpolled_matches(tournament_id, round_num)

    if not matches:
        logger.warning("No unpolled matches found for tournament %s, round %s.", tournament_id, round_num)
        return

    # Calculate the timestamp when these polls will close
    end_time = datetime.now(timezone.utc) + timedelta(days=days_per_round)

    for match in matches:
        try:
            # Create the Poll object
            poll = discord.Poll(
                question=f"Round {round_num} | {match['a_name']} vs {match['b_name']}",
                duration=timedelta(days=days_per_round),
                multiple=False  # Only allow voting for one option
            )
            poll.add_answer(text=match['a_name'])
            poll.add_answer(text=match['b_name'])

            # Post it to the channel
            message = await channel.send(poll=poll)

            # Store the matchup
            set_match_poll_data(match['match_id'], message.id, end_time)

        except Exception as ex:
            logger.error("Failed to post poll for match %s: %s", match['match_id'], ex)


logger = logging.getLogger('iu-bot')

@tasks.loop(minutes=5)
async def tournament_resolution_loop(client: discord.Client, guild_id: int):
    """Wakes up every 5 minutes to resolve expired tournament polls."""
    logger.info("Running tournament resolution loop...")
    guild = client.get_guild(guild_id)
    if not guild:
        logger.error("Could not find guild with ID: %s", guild_id)
        return

    tournaments_channel = discord.utils.get(guild.channels, name="tournaments")
    if not tournaments_channel:
        logger.error("Could not find #tournaments channel to resolve polls.")
        return

    expired_matches = get_expired_unresolved_matches()
    if len(expired_matches) > 0:
        logger.info("Found %d expired matches to resolve.", len(expired_matches))
        await _process_expired_matches(tournaments_channel, expired_matches)
        t_id = expired_matches[0]['tournament_id']

        # Let Discord's backend catch up and post all "Poll Closed" messages
        await asyncio.sleep(max(10,2*len(expired_matches)))
    else:
        t_id = get_active_tournament_id()
        if not t_id:
            logger.info("No active tournament found, skipping round completion check.")
            return

    await check_round_completion(tournaments_channel, t_id, get_tournament_days(t_id))

async def _process_expired_matches(tournaments_channel, expired_matches):
    for match in expired_matches:
        try:
            # Fetch the actual Discord message
            message = await tournaments_channel.fetch_message(match['message_id'])
            poll = message.poll

            if not poll:
                logger.error("Message %s is not a poll!", match['message_id'])
                continue

            # Tally the votes
            # We map the first answer to entrant_a, second to entrant_b
            ans_a = poll.answers[0]
            ans_b = poll.answers[1]
            votes_a = ans_a.vote_count
            votes_b = ans_b.vote_count

            # Determine Winner
            if votes_a > votes_b:
                winner_id = match['entrant_a_id']
                winner_name = ans_a.text
            elif votes_b > votes_a:
                winner_id = match['entrant_b_id']
                winner_name = ans_b.text
            else:
                # Tie is broken by the higher seed
                seed_a = match.get('entrant_a_seed', 99)
                seed_b = match.get('entrant_b_seed', 99)
                if seed_a < seed_b:
                    winner_id = match['entrant_a_id']
                    winner_name = poll.answers[0].text
                else:
                    winner_id = match['entrant_b_id']
                    winner_name = poll.answers[1].text

            # Advance the winner in the database
            success = advance_winner(
                match_id=match['match_id'],
                tournament_id=match['tournament_id'],
                current_round=match['round_num'],
                current_pos=match['match_position'],
                winner_id=winner_id
            )

            if success:
                logger.info("Match %s resolved: %s won.", match['match_id'], winner_name)
                if not poll.is_finalised():
                    await message.end_poll()

        except discord.NotFound:
            logger.error("Poll message %s was deleted by a user.", match['message_id'])
        except Exception as ex:
            logger.error("Error resolving match %s: %s", match['match_id'], ex)

async def check_round_completion(channel: discord.TextChannel, tournament_id: str, days_per_round: int):
    """
    Triggers round transitions or the final championship announcement.
    """
    status = check_round_status(tournament_id)
    current_round = status['current_round']
    t_name = status['tournament_name']

    # Handle the Grand Finale if the entire tournament is finished
    if status.get('is_tournament_over'):
        set_tournament_completed(tournament_id)

        image_buffer = await generate_bracket_image(tournament_id)
        winner_name = get_tournament_winner_name(tournament_id)
        finale_msg = (
            f"The *{t_name}** tournament has concluded, and the Grand Champion is **{winner_name}**!"
        )

        # Run the participation raffle
        raffle_data = get_tournament_raffle_winner(tournament_id)
        if raffle_data:
            winner_id = raffle_data['user_id']
            tickets = raffle_data['tickets']
            total_pool = raffle_data['total_pool']

            # Award the winner with 5 hearts
            modify_db_balance("IU bot", winner_id, 5, f"Won the raffle for {t_name}!")

            guild = channel.guild
            news_channel = discord.utils.get(guild.text_channels, name="dispatch-news")
            if news_channel:
                # Safely fetch the member to ping them
                member = await guild.fetch_member(winner_id)
                msg = (
                    f"{member.mention} earned **5 hearts** for winning the participation raffle "
                    f"for the **{t_name}**!"
                )
                await news_channel.send(msg)

            member = await guild.fetch_member(winner_id)
            finale_msg += (
                f"\n\n**Participation Raffle**\n"
                f"Every vote cast was a ticket in our Grand Prize draw (Total Pool: {total_pool} votes).\n"
                f"Congratulations to {member.mention}! You had {tickets} votes in the raffle, and one was pulled! "
                "You've earned **5 hearts** as a result!"
            )

        file = None
        if image_buffer:
            image_buffer.seek(0)
            file = discord.File(fp=image_buffer, filename="bracket_final.png")

        await channel.send(content=finale_msg, file=file)
        return

    # Check if the active round needs its polls posted
    unpolled_matches = get_unpolled_matches(tournament_id, current_round)
    if not unpolled_matches:
        # No new polls to post. This means the round is currently ongoing and we're just waiting.
        logger.info("Tournament %s round %s is ongoing.", tournament_id, current_round)
        return

    # If there are unpolled matches, we just crossed the boundary into a new round!
    previous_round = current_round - 1
    image_buffer = await generate_bracket_image(tournament_id)
    if previous_round > 0:
        await channel.send(f"**Round {previous_round} is now complete!**")

        if image_buffer:
            image_buffer.seek(0)
            file = discord.File(fp=image_buffer, filename=f"bracket_r{previous_round}_complete.png")
            await channel.send(content="Here is the updated tournament bracket:", file=file)

    # Post the new polls
    await channel.send(f"**Round {current_round} starts now!**")
    await post_round_polls(channel, tournament_id, current_round, days_per_round)
