import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./client/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
  	container: {
  		center: true,
  		padding: '2rem',
  		screens: {
  			'2xl': '1400px'
  		}
  	},
  	extend: {
  		fontSize: {
  			// Bumped over Tailwind defaults for legibility. The client's staff
  			// skew older and reported having to change browser magnification to
  			// read the app.
  			//
  			// The first pass raised these tokens but the complaint persisted,
  			// because ~320 places hardcoded text-[9px]…text-[13px] and so never
  			// saw the token at all. Those were swept to text-xs; THAT was the
  			// substantive fix. This second, smaller bump lifts xs and sm — where
  			// nearly all UI text lives (~2,400 usages) — by a further 1px.
  			//
  			// base/lg/xl are left alone: headings were never the complaint, and
  			// growing them costs vertical space on dense clinical screens.
  			// Oct 2026 (go-live): staff read the app zoomed out so whole tables fit on screen; xs/sm went up again
  			// and table cells lost horizontal padding instead, so pages keep their width.
  			xs:   ['0.9375rem', { lineHeight: '1.375rem' }],  // 15px (Tailwind: 12px)
  			sm:   ['1.0625rem', { lineHeight: '1.5625rem'}],  // 17px (Tailwind: 14px)
  			base: ['1.0625rem', { lineHeight: '1.625rem' }],  // 17px (Tailwind: 16px)
  			lg:   ['1.1875rem', { lineHeight: '1.75rem'  }],  // 19px (Tailwind: 18px)
  			xl:   ['1.3125rem', { lineHeight: '1.875rem' }],  // 21px (Tailwind: 20px)
  		},
  		colors: {
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			sidebar: {
  				DEFAULT: 'hsl(var(--sidebar-background))',
  				foreground: 'hsl(var(--sidebar-foreground))',
  				primary: 'hsl(var(--sidebar-primary))',
  				'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
  				accent: 'hsl(var(--sidebar-accent))',
  				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
  				border: 'hsl(var(--sidebar-border))',
  				ring: 'hsl(var(--sidebar-ring))',
  				'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
  				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))'
  			},
  			warning: {
  				DEFAULT: 'hsl(var(--warning))',
  				foreground: 'hsl(var(--warning-foreground))'
  			},
  			success: {
  				DEFAULT: 'hsl(var(--success))',
  				foreground: 'hsl(var(--success-foreground))'
  			},
  			info: {
  				DEFAULT: 'hsl(var(--info))',
  				foreground: 'hsl(var(--info-foreground))'
  			},
  			gold: {
  				DEFAULT: 'hsl(var(--gold))',
  				foreground: 'hsl(var(--gold-foreground))'
  			},
  			surface: {
  				'0': 'hsl(var(--background-0))',
  				'1': 'hsl(var(--background-1))',
  				'2': 'hsl(var(--background-2))',
  				'3': 'hsl(var(--background-3))'
  			}
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)',
  			xl: 'calc(var(--radius) + 0.25rem)',
  			'2xl': 'calc(var(--radius) + 0.5rem)'
  		},
  		boxShadow: {
  			'elevation-1': 'var(--shadow-elevation-1)',
  			'elevation-2': 'var(--shadow-elevation-2)',
  			'elevation-3': 'var(--shadow-elevation-3)',
  			glow: 'var(--shadow-glow)'
  		},
  		backgroundImage: {
  			'gradient-primary': 'var(--gradient-primary)',
  			'gradient-soft': 'var(--gradient-soft)'
  		},
  		transitionTimingFunction: {
  			smooth: 'cubic-bezier(0.4, 0, 0.2, 1)'
  		},
  		keyframes: {
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		},
  		animation: {
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
