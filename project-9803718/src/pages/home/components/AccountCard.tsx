import { Account } from "@/mocks/accounts";

interface AccountCardProps {
  account: Account;
}

export default function AccountCard({ account }: AccountCardProps) {
  const xbActive = account.xbLinked === true;
  const psnActive = account.psnLinked === true;

  return (
    <button className="group w-full text-left bg-card border border-border rounded-2xl overflow-hidden hover:glow-primary-sm hover:border-primary/20 transition-all duration-200 animate-fade-in cursor-pointer">
      {/* Image area */}
      <div className="relative aspect-[3/2] overflow-hidden bg-secondary">
        {account.imageUrl ? (
          <img
            src={account.imageUrl}
            alt={account.title}
            className="w-full h-full object-cover object-top group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <i className="ri-gamepad-line text-muted-foreground/20 text-5xl w-12 h-12 flex items-center justify-center" />
          </div>
        )}

        {/* Gradient overlay */}
        <div className="absolute inset-0 gradient-card-overlay" />

        {/* Price badge — bottom left */}
        <div className="absolute bottom-2.5 left-2.5 px-2.5 py-1 rounded-lg bg-primary/90 backdrop-blur-sm">
          <span className="text-xs font-bold text-primary-foreground font-display tracking-wide">
            {account.price.toFixed(2)} €
          </span>
        </div>

        {/* Active badge */}
        {account.isActive && (
          <div className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded-full bg-destructive/90 backdrop-blur-sm flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-destructive-foreground animate-pulse inline-block" />
            <span className="text-[9px] font-bold text-destructive-foreground uppercase tracking-widest">Active</span>
          </div>
        )}

        {/* Platform badges — top left */}
        <div className="absolute top-2.5 left-2.5 flex gap-1">
          {xbActive && (
            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-md bg-black/60 text-green-400 border border-green-400/30 backdrop-blur-sm">
              XB
            </span>
          )}
          {psnActive && (
            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-md bg-black/60 text-blue-400 border border-blue-400/30 backdrop-blur-sm">
              PS
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-3">
        <h3 className="text-sm font-bold text-foreground line-clamp-1 group-hover:text-primary transition-colors tracking-wide font-display">
          {account.title}
        </h3>

        {/* Stats row */}
        <div className="mt-2 flex items-center gap-0 divide-x divide-border border border-border rounded-lg overflow-hidden">
          <div className="flex-1 flex flex-col items-center py-1.5 gap-0.5 hover:bg-secondary/50 transition-colors">
            <i className="ri-t-shirt-line text-primary text-xs w-3.5 h-3.5 flex items-center justify-center" />
            <span className="text-[10px] font-bold text-foreground">{account.skins.toLocaleString()}</span>
            <span className="text-[8px] text-muted-foreground uppercase tracking-wider">Skins</span>
          </div>
          <div className="flex-1 flex flex-col items-center py-1.5 gap-0.5 hover:bg-secondary/50 transition-colors">
            <i className="ri-copper-diamond-line text-primary text-xs w-3.5 h-3.5 flex items-center justify-center" />
            <span className="text-[10px] font-bold text-foreground">{account.vbucks.toLocaleString()}</span>
            <span className="text-[8px] text-muted-foreground uppercase tracking-wider">V-Bucks</span>
          </div>
          {account.hasEmail && (
            <div className="flex-1 flex flex-col items-center py-1.5 gap-0.5 hover:bg-secondary/50 transition-colors">
              <i className="ri-mail-check-line text-primary text-xs w-3.5 h-3.5 flex items-center justify-center" />
              <span className="text-[10px] font-bold text-primary">Yes</span>
              <span className="text-[8px] text-muted-foreground uppercase tracking-wider">Email</span>
            </div>
          )}
        </div>
      </div>
    </button>
  );
}