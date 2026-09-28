library ieee;
use ieee.std_logic_1164.all;

library lib_a;

entity top is
  port (
    clk : in std_ulogic;
    d : in std_ulogic_vector(7 downto 0);
    q : out std_ulogic_vector(7 downto 0)
  );
end entity;

architecture rtl of top is
  signal mid_q : std_ulogic_vector(7 downto 0);
begin
  leaf_inst : entity lib_a.leaf
    generic map (
      width => 8
    )
    port map (
      clk => clk,
      d => d,
      q => mid_q
    );

  gen_mid : if true generate
    mid_inst : entity work.mid
      port map (
        clk => clk,
        d => mid_q,
        q => q
      );
  end generate;
end architecture;
