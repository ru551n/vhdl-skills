library ieee;
use ieee.std_logic_1164.all;

use work.pkg_a.all;

entity leaf is
  generic (
    width : positive := 8
  );
  port (
    clk : in std_ulogic;
    d : in std_ulogic_vector(width - 1 downto 0);
    q : out std_ulogic_vector(width - 1 downto 0)
  );
end entity;

architecture rtl of leaf is
  signal state : state_t := idle;
begin
  process (clk)
  begin
    if rising_edge(clk) then
      q <= d;
      state <= busy;
    end if;
  end process;
end architecture;
