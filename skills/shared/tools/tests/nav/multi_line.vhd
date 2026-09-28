library ieee;
use ieee.std_logic_1164.all;

entity multi is
  generic (
    widths : integer_vector := (
      8, 16, 32
    )
  );
  port (
    clk : in std_ulogic;
    data : out std_ulogic_vector(
      15 downto 0
    ); -- trailing comment
    a, b : in std_ulogic
  );
end entity;

architecture rtl of multi is
  signal sel : natural range 0 to
    3;
begin
  g : if sel = 0 generate
    u : entity work.leaf port map (clk => clk);
  elsif sel = 1 generate
    u : entity work.leaf port map (clk => clk);
  else generate
    u : entity work.leaf port map (clk => clk);
  end generate;
end architecture;
