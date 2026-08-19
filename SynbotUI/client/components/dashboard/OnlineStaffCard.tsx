import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Users, Circle } from "lucide-react";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export function OnlineStaffCard() {
  const [open, setOpen] = useState(false);

  const { data } = useQuery({
    queryKey: ["presence-summary"],
    queryFn: () => api.presence.summary(),
    refetchInterval: 25_000,
  });

  const count = data?.count ?? 0;
  const staff = data?.staff ?? [];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Card className="border-green-500/20 cursor-pointer hover:border-green-500/40 transition-colors">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[13px] text-muted-foreground">Online Now</p>
                <p className="text-2xl font-bold">{count}</p>
                <p className="text-sm text-muted-foreground mt-0.5">staff logged in</p>
              </div>
              <div className="relative">
                <Users className="h-4 w-4 text-green-400 mt-0.5" />
                {count > 0 && (
                  <Circle className="h-2 w-2 fill-green-400 text-green-400 absolute -top-0.5 -right-0.5" />
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <div className="px-3 py-2 border-b">
          <p className="text-sm font-semibold">{count} online now</p>
        </div>
        <div className="max-h-72 overflow-y-auto">
          {staff.length === 0 ? (
            <p className="text-sm text-muted-foreground px-3 py-4 text-center">No one else is online right now.</p>
          ) : (
            <ul className="divide-y">
              {staff.map((s: any) => (
                <li key={s.user_id} className="px-3 py-2 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{s.full_name}</p>
                    <p className="text-sm text-muted-foreground truncate capitalize">
                      {[s.role, s.department].filter(Boolean).join(" · ") || "—"}
                    </p>
                  </div>
                  <Circle className={cn("h-2 w-2 fill-green-400 text-green-400 shrink-0")} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
