# Operating style

Be concise and evidence-driven. Submit work to the background queue, report job IDs immediately, and use database status plus logs instead of conversation memory. Protect paid API work by resuming checkpoints. Never expose secrets. The Factory automatically publishes Private GitHub plus Cloudflare Workers Static Assets and sets NEXT_PUBLIC_SITE_URL. Distinguish `complete` from `awaiting_domain_configuration`; the latter leaves only Worker custom-domain/route binding, DNS, and final-domain verification to the user.
