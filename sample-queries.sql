-- Get accounts a user follows
select n.username, nf.username
from node n
join edge following
on n.user_id = following.from_id
join node nf
on following.to_id = nf.user_id
where n.username = 'jtv_fan'
order by n.username, nf.username



-- Get followers of an account
select n.username, nf.username from node n
join edge followers
on n.user_id = followers.to_id
join node nf
on followers.from_id = nf.user_id
where n.username = 'jtv_fan'
order by n.username, nf.username



-- Find accounts that multiple members of a node_type (target group) are
-- following. Matches are ranked based on how many members of the target
-- group are following an account.
select nf.user_id, nf.username, nf.url, count(*) as [MutualCount]
from node n
join edge following
on n.user_id = following.from_id
join node nf
on following.to_id = nf.user_id
where
    -- Find mutuals between members of this node_type.
    n.node_type = 'bad_actors'

    -- Ignore useless accounts like stores or products. Copy
    -- more of these lines if necessary. The % are wildcards,
    -- place your ignored search term in between
    AND nf.username not like '%boutique%'

    -- Ignore verified users - they probably aren't of interest to OSINT investigations
    AND nf.is_verified = 0
    AND nf.node_type is null
group by nf.user_id, nf.username, nf.url
-- Threshold requiring matches to be followed by more than one account
-- in the target group. You can increase this number if you have a lot
-- of members in target group.
HAVING count(*) > 1
order by count(*) desc



-- Find accounts that are following multiple members of interest.
-- Matches are ranked based on how many members of the target
-- group the account follows.
select nf.user_id, nf.username, nf.url, count(*) as [FollowingCount]
from node n
join edge following
on n.user_id = following.to_id
join node nf
on following.from_id = nf.user_id
where 
  -- Filter for specific accounts in target group
  n.username in ('jtv_fan', 'janethevirgin.cw')

  -- Ignore useless accounts like stores or products. Copy
  -- more of these lines if necessary. The % are wildcards,
  -- place your ignored search term in between
  AND nf.username not like '%boutique%'

  -- Ignore verified users - they probably aren't of interest to OSINT investigations
  AND nf.is_verified = 0
  AND nf.node_type is null
group by nf.user_id, nf.username, nf.url
-- Threshold requiring matches to follow more than one account
-- in the list of accounts. You can increase this number to require
-- an account to follow more members when counting.
HAVING count(*) > 1
order by count(*) desc
